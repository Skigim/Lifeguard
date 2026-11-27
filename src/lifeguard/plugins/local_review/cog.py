"""Send Discord prompts to a connected agent and handle explicit issue requests."""

from __future__ import annotations

import asyncio
import re
from contextlib import suppress
from typing import TYPE_CHECKING

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from gidgethub import GitHubException

from lifeguard.core.github.client import RelinkRequired
from lifeguard.core.github.store import Store
from lifeguard.core.github.web import link_url
from lifeguard.core.loader import ProcessDisabled
from lifeguard.core.plugins import PluginCog
from lifeguard.core.replies import reply as private_reply

from .process import Followup, LocalReview, ReviewError, ReviewResult
from .references import Reference, References

if TYPE_CHECKING:
    from lifeguard.bot import LifeguardBot
    from lifeguard.core.github.service import GitHubService

ISSUE_REQUEST = re.compile(
    r"(?:(?:can|could|would)\s+you\s+)?(?:please\s+)?"
    r"(?:(?:review|read|look\s+through)\s+(?:this|the)\s+"
    r"(?:discussion(?:\s+thread)?|thread)(?:\s*,\s*|\s+)and\s+)?"
    r"(?:add|create|file|open)\s+(?:(?:an?|any|the|relevant|actionable|new|github)\s+)*issues?"
    r"(?:\s+(?:to|on|in)\s+github)?"
    r"(?:\s+from\s+(?:this|the)\s+(?:discussion(?:\s+thread)?|thread))?[.!?]?"
    r"(?:\s+repo:(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?))?[.!?]?",
    re.IGNORECASE,
)
MAX_MESSAGES = 80
MAX_CONTEXT_CHARS = 8000
CONTEXT_NOTICE = "\nI used the most recent messages within the context limit."
REPO_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
PR_NUMBER = re.compile(r"(?:\b(?:pr|pull request)\s*#?\s*|#|/pull/)([1-9]\d*)\b", re.I)
PR_LINK = re.compile(r"https://github\.com/([\w.-]+/[\w.-]+)/pull/([1-9]\d*)\b", re.I)
REVIEW_DOCS = "https://github.com/Skigim/Lifeguard/blob/main/docs/features/local-review.md"


def require_github(reviewer: LocalReview) -> GitHubService:
    if reviewer.github is None:
        raise ReviewError("Ask the bot operator to configure GitHub first.")
    return reviewer.github


async def select_repo(
    store: Store, channel: discord.abc.GuildChannel | discord.Thread, requested: str | None
) -> str:
    guild_id = channel.guild.id
    configured = await store.one(
        "SELECT repo FROM local_review_repos WHERE guild_id=?", (guild_id,)
    )
    if requested is not None:
        requested = requested.lower()
        if configured is not None and requested == configured["repo"]:
            return requested
        link = await store.one(
            "SELECT repo FROM repo_links WHERE guild_id=? AND repo=?",
            (guild_id, requested),
        )
        if link is None:
            raise ReviewError("Choose a GitHub repository configured for this server.")
        return link["repo"]

    if configured is not None:
        return configured["repo"]

    if isinstance(channel, discord.Thread):
        if post := await store.one(
            "SELECT repo FROM posts JOIN repo_links USING (guild_id, repo) "
            "WHERE guild_id=? AND thread_id=?",
            (guild_id, channel.id),
        ):
            return post["repo"]
        links = await store.all(
            "SELECT repo FROM repo_links WHERE guild_id=? AND forum_id=? LIMIT 2",
            (guild_id, channel.parent_id),
        )
        if len(links) == 1:
            return links[0]["repo"]
    links = await store.all("SELECT repo FROM repo_links WHERE guild_id=? LIMIT 2", (guild_id,))
    if len(links) == 1:
        return links[0]["repo"]
    if not links:
        raise ReviewError(
            "Ask a server admin to set a repository with `/lg setup repo:owner/repo`."
        )
    raise ReviewError("Add `repo:owner/repo` to choose a linked GitHub repository.")


async def thread_context(
    thread: discord.Thread, request: discord.Message
) -> tuple[list[str], bool]:
    messages = []
    remaining = MAX_CONTEXT_CHARS
    seen = 0
    async for message in thread.history(limit=MAX_MESSAGES + 1, before=request):
        seen += 1
        if seen > MAX_MESSAGES:
            return messages[::-1], True
        if message.type is discord.MessageType.thread_starter_message:
            # Text-channel threads can start with a reference to a message in the parent.
            parent = thread.parent
            if not isinstance(parent, discord.TextChannel):
                continue
            try:
                starter = thread.starter_message
                if starter is None or starter.type is discord.MessageType.thread_starter_message:
                    starter = await parent.fetch_message(thread.id)
                message = starter
            except (discord.Forbidden, discord.NotFound):
                continue
        if message.author.bot or message.is_system():
            continue
        content = message.content.strip()
        if not content:
            continue
        if len(content) > remaining:
            return messages[::-1], True
        messages.append(content)
        remaining -= len(content)
    return messages[::-1], False


class LocalReviewCog(PluginCog):
    def __init__(self, bot: LifeguardBot) -> None:
        self.bot = bot
        self.review_lock = asyncio.Lock()
        self.references = References()
        self.guild_commands = app_commands.Group(
            name="lg", description="Set up and configure local review", guild_only=True
        )
        self.guild_commands.command(name="hook", description="Show the local agent hook")(self.hook)
        self.guild_commands.command(name="setup", description="Set up your local review agent")(
            self.setup_agent
        )
        self.guild_commands.command(name="config", description="Set or view the mention role")(
            self.configure_mentions
        )

    async def hook(self, interaction: discord.Interaction) -> None:
        assert interaction.guild_id is not None
        reviewer = self.bot.loader.require(LocalReview.name, interaction.guild_id)
        settings = reviewer.settings
        if settings.host in {"127.0.0.1", "localhost", "::1", "0.0.0.0"}:
            host = {"::1": "[::1]", "0.0.0.0": "127.0.0.1"}.get(settings.host, settings.host)
            address = f"On the Lifeguard host or container, use `http://{host}:{settings.port}`."
        else:
            address = f"The hook listens on port `{settings.port}` on the Lifeguard host."
        await private_reply(
            interaction,
            f"**Local review is enabled in this server.** {address}\n"
            "Use `Authorization: Bearer <LOCAL_REVIEW_TOKEN>` on each request.\n"
            "- `GET /v1/health` checks connectivity and authentication.\n"
            "- `POST /v1/jobs/next?include_replies=true&include_references=true` claims requests.\n"
            "- `POST /v1/jobs/{id}/result` returns the reply or issue drafts.\n"
            "Run `/lg setup` for connection and account-linking steps.",
        )

    @app_commands.describe(repo="Set this server's default GitHub repository as owner/repo")
    async def setup_agent(self, interaction: discord.Interaction, repo: str | None = None) -> None:
        assert interaction.guild_id is not None
        reviewer = self.bot.loader.require(LocalReview.name, interaction.guild_id)
        message = "Choose where Lifeguard runs. Your agent can run on your own machine either way."
        if repo is not None:
            if not interaction.permissions.manage_guild:
                await private_reply(
                    interaction, "Manage Server permission is required to set a repo."
                )
                return
            if reviewer.github is None:
                await private_reply(interaction, "Ask the bot operator to configure GitHub first.")
                return
            repo = repo.strip().lower()
            if REPO_PATTERN.fullmatch(repo) is None:
                await private_reply(interaction, "Use `owner/repo` for the repository.")
                return
            await interaction.response.defer(ephemeral=True)
            try:
                await reviewer.github.gh.get_repo_installation(repo)
            except (GitHubException, aiohttp.ClientError, TimeoutError):
                await private_reply(
                    interaction, "Check that the GitHub App is installed on that repo."
                )
                return
            self.bot.loader.require(LocalReview.name, interaction.guild_id)
            await reviewer.github.store.put(
                "local_review_repos", guild_id=interaction.guild_id, repo=repo
            )
            message = f"Default repository set to `{repo}`. " + message
        await private_reply(interaction, message, view=SetupView(self))

    @app_commands.describe(role="Role required to mention or follow up with Lifeguard")
    async def configure_mentions(
        self, interaction: discord.Interaction, role: discord.Role | None = None
    ) -> None:
        guild = interaction.guild
        assert guild is not None
        reviewer = self.bot.loader.require(LocalReview.name, guild.id)
        if not interaction.permissions.manage_guild:
            await private_reply(
                interaction, "Manage Server permission is required to configure mentions."
            )
            return
        if role is None:
            role_id = reviewer.mention_roles.get(guild.id)
            configured = guild.get_role(role_id) if role_id is not None else None
            if configured is not None:
                message = f"Members with {configured.mention} can use mentions and follow-ups."
            elif role_id is not None:
                message = "The configured role was deleted. Choose a new role with `/lg config`."
            else:
                message = "Mentions are locked. Choose a role with `/lg config`."
        elif role.is_default():
            message = "Choose a role that can be assigned to individual members."
        else:
            await reviewer.set_mention_role(guild.id, role.id)
            message = f"Members with {role.mention} can now mention or follow up with Lifeguard."
        await private_reply(interaction, message)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        user = self.bot.user
        if user is None or message.guild is None or message.webhook_id:
            return
        if message.author.bot and message.author.id != user.id:
            return
        guild_id = message.guild.id
        try:
            reviewer = self.bot.loader.require(LocalReview.name, guild_id)
        except ProcessDisabled:
            return
        if message.author.id == user.id:
            self.references.remember(message)
            return
        role_id = reviewer.mention_roles.get(guild_id)
        if (
            role_id is None
            or not isinstance(message.author, discord.Member)
            or message.author.get_role(role_id) is None
        ):
            return
        tag = rf"<@!?{user.id}>"
        mention = re.match(rf"\s*{tag}[\s,]*", message.content)
        text = message.content[mention.end() :] if mention else message.content
        try:
            reference, prompt = await self.references.resolve(message, user.id, text.strip())
        except discord.HTTPException:
            if mention:
                await self.reply(message, "Discord could not read the referenced message.")
            return
        if reference is None and mention is None:
            if not re.search(tag, prompt) or not any(u.id == user.id for u in message.mentions):
                return
            reference = Reference("mention", None)
            prompt = re.sub(tag, "@Lifeguard", prompt)
        if not prompt:
            await self.reply(message, "Add a question or request after the mention.")
            return
        if self.review_lock.locked():
            if mention:
                await self.reply(
                    message, "An agent is already handling a request. Try again shortly."
                )
            return
        async with self.review_lock:
            try:
                if reference is not None:
                    await self.follow_up(message, reviewer, prompt, reference, bool(mention))
                elif issue_request := ISSUE_REQUEST.fullmatch(prompt):
                    if not isinstance(message.channel, discord.Thread):
                        await self.reply(message, "Ask me to file issues from inside the thread.")
                        return
                    await self.review_thread(
                        message, message.channel, reviewer, prompt, issue_request["repo"]
                    )
                else:
                    response, scope = await self.ask_agent(message, reviewer, prompt)
                    assert isinstance(response, str)
                    await self.reply(message, response + scope)
            except ProcessDisabled:
                await self.reply(message, "Local review was disabled in this server.")
            except (ReviewError, RelinkRequired) as exc:
                await self.reply(message, str(exc))
            except discord.Forbidden:
                await self.reply(
                    message, "I need permission to read the discussion and reply here."
                )
            except discord.HTTPException:
                await self.reply(message, "Discord could not complete the request.")

    async def follow_up(
        self,
        message: discord.Message,
        reviewer: LocalReview,
        prompt: str,
        reference: Reference,
        mentioned: bool,
    ) -> None:
        assert message.guild is not None
        try:
            # Passive discussion should leave no visible typing or error message.
            result = await reviewer.review(
                message.guild.id,
                prompt,
                None,
                [],
                False,
                reference={
                    "kind": reference.kind,
                    "content": reference.content,
                    "mentioned": mentioned,
                },
            )
        except ReviewError:
            if mentioned:
                raise
            return
        assert isinstance(result, Followup)
        if result.action == "ignore":
            return
        if reference.kind == "mention" and result.action not in {"reply", "react"}:
            return
        self.require_current(message, reviewer)
        if result.action == "reply":
            await self.reply(message, result.text)
        elif result.action == "react":
            with suppress(discord.HTTPException):
                await message.add_reaction(result.text)
        elif result.action == "post_pr_comment":
            await self.post_pr_comment(message, reviewer, result, prompt, reference.content)
        else:
            github = require_github(reviewer)
            repo = await select_repo(github.store, message.channel, result.repo)
            await self.publish_issues(message, reviewer, repo, result.issues)

    def require_current(self, message: discord.Message, reviewer: LocalReview) -> None:
        assert message.guild is not None
        if self.bot.loader.require(LocalReview.name, message.guild.id) is not reviewer:
            raise ReviewError("Local review restarted. Send a new request to try again.")

    async def ask_agent(
        self,
        message: discord.Message,
        reviewer: LocalReview,
        prompt: str,
        *,
        repo: str | None = None,
    ) -> tuple[ReviewResult, str]:
        assert message.guild is not None
        channel = message.channel
        title = None
        context, limited = [], False
        if isinstance(channel, discord.Thread):
            title = channel.name
            context, limited = await thread_context(channel, message)
        if repo is not None and not context:
            raise ReviewError("I found no discussion text before your request.")
        guild_id = message.guild.id
        self.require_current(message, reviewer)
        async with channel.typing():
            result = await reviewer.review(guild_id, prompt, title, context, limited, repo=repo)
        self.require_current(message, reviewer)
        return result, CONTEXT_NOTICE if limited else ""

    async def review_thread(
        self,
        message: discord.Message,
        thread: discord.Thread,
        reviewer: LocalReview,
        prompt: str,
        requested_repo: str | None,
    ) -> None:
        store = require_github(reviewer).store
        if await store.one("SELECT 1 FROM local_review_requests WHERE message_id=?", (message.id,)):
            return
        repo = await select_repo(store, thread, requested_repo)
        author_id = message.author.id
        if not await store.one("SELECT 1 FROM user_links WHERE discord_id=?", (author_id,)):
            raise ReviewError("Link your GitHub account from `/lg setup` first.")
        issues, scope = await self.ask_agent(message, reviewer, prompt, repo=repo)
        assert isinstance(issues, list)
        await self.publish_issues(message, reviewer, repo, issues, scope)

    async def publish_issues(
        self,
        message: discord.Message,
        reviewer: LocalReview,
        repo: str,
        issues: list[tuple[str, str]],
        scope: str = "",
    ) -> None:
        if not issues:
            await self.reply(message, "I found no actionable GitHub issues." + scope)
            return

        github = require_github(reviewer).gh
        token = await self.linked_token(github, message.author.id)
        if not await self.claim_write(message, reviewer, repo):
            return

        links = []
        failure = ""
        for title, body in issues:
            try:
                issue = await github.create_issue(
                    repo, title, f"{body}\n\nSource discussion: {message.jump_url}", token
                )
            except (GitHubException, aiohttp.ClientError, TimeoutError) as exc:
                if getattr(exc, "status_code", None) in {403, 404}:
                    failure = "GitHub denied access to that repository."
                else:
                    failure = "GitHub stopped the batch. Check the repository before trying again."
                break
            links.append(f"[`{repo}#{issue['number']}`]({issue['html_url']})")

        result = []
        if links:
            result.append("Opened " + ", ".join(links) + ".")
        if failure:
            result.append(failure)
        await self.reply(message, "\n".join(result) + scope)

    async def post_pr_comment(
        self,
        message: discord.Message,
        reviewer: LocalReview,
        result: Followup,
        prompt: str,
        reference: str | None,
    ) -> None:
        target = prompt if PR_NUMBER.search(prompt) else reference or ""
        identifiers = set(PR_NUMBER.findall(target))
        linked_repos = {repo.lower() for repo, _ in PR_LINK.findall(target)}
        if (
            result.pr_number is None
            or identifiers != {str(result.pr_number)}
            or len(linked_repos) > 1
        ):
            await self.reply(
                message, "Which pull request should I comment on? Send its link or number."
            )
            return
        service = require_github(reviewer)
        requested_repo = next(iter(linked_repos)) if linked_repos else result.repo
        repo = await select_repo(service.store, message.channel, requested_repo)
        github = service.gh
        token = await self.linked_token(github, message.author.id)
        try:
            await github.get_pull_request(repo, result.pr_number, token)
        except (GitHubException, aiohttp.ClientError, TimeoutError) as exc:
            raise ReviewError(
                "I couldn’t verify that pull request. Check its link and your access."
            ) from exc
        if not await self.claim_write(message, reviewer, repo):
            return
        try:
            comment = await github.create_comment(repo, result.pr_number, result.text, token)
        except (GitHubException, aiohttp.ClientError, TimeoutError) as exc:
            raise ReviewError(
                "GitHub couldn’t confirm the comment. Check the PR before retrying."
            ) from exc
        await self.reply(
            message, f"Posted a [comment on `{repo}#{result.pr_number}`]({comment['html_url']})."
        )

    @staticmethod
    async def linked_token(github, author_id: int) -> str:
        try:
            return await github.user_token(author_id)
        except RelinkRequired as exc:
            raise ReviewError("Link your GitHub account from `/lg setup` first.") from exc
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise ReviewError("GitHub could not check your linked account.") from exc

    async def claim_write(self, message: discord.Message, reviewer: LocalReview, repo: str) -> bool:
        self.require_current(message, reviewer)
        store = require_github(reviewer).store
        await select_repo(store, message.channel, repo)
        return bool(
            await store.execute(
                "INSERT OR IGNORE INTO local_review_requests VALUES (?)", (message.id,)
            )
        )

    @staticmethod
    async def reply(message: discord.Message, content: str) -> None:
        await message.channel.send(
            content,
            reference=message.to_reference(fail_if_not_exists=False),
            allowed_mentions=discord.AllowedMentions.none(),
            silent=True,
        )


class SetupView(discord.ui.View):
    def __init__(self, cog: LocalReviewCog) -> None:
        super().__init__(timeout=300)
        self.cog = cog

    async def show_steps(self, interaction: discord.Interaction, endpoint: str) -> None:
        await interaction.response.edit_message(
            content=(
                f"1. {endpoint}\n"
                "2. Give your agent `LOCAL_REVIEW_TOKEN` through its local environment. "
                "Use the same token as the Lifeguard operator.\n"
                "3. Make an authenticated `GET /v1/health` request. A `200` confirms access. "
                "Then start the agent using the polling endpoint from `/lg hook`.\n"
                "4. Mention Lifeguard followed by your prompt. For issue creation, "
                "click **Link GitHub** first.\n\n"
                f"[Connection examples and the agent protocol]({REVIEW_DOCS})"
            ),
        )

    @discord.ui.button(label="Same machine")
    async def same_machine(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await self.show_steps(
            interaction,
            "Run the agent on the Lifeguard machine. The default URL is `http://127.0.0.1:8090`. "
            "Use `/lg hook` for the configured port and the published host port if using Docker.",
        )

    @discord.ui.button(label="Another machine")
    async def another_machine(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await self.show_steps(
            interaction,
            "Ask the bot operator for a private hook URL reachable from your computer. "
            "A loopback listener needs a private tunnel or port forward to reach it remotely.",
        )

    @discord.ui.button(label="Link GitHub", style=discord.ButtonStyle.primary)
    async def link_github(self, interaction: discord.Interaction, _button: discord.ui.Button):
        assert interaction.guild_id is not None
        try:
            reviewer = self.cog.bot.loader.require(LocalReview.name, interaction.guild_id)
        except ProcessDisabled:
            await private_reply(interaction, "Local review is disabled in this server.")
            return
        if reviewer.github is None:
            await private_reply(interaction, "Ask the bot operator to configure GitHub first.")
            return
        view = discord.ui.View(timeout=600)
        url = await link_url(reviewer.github, interaction.user.id)
        view.add_item(discord.ui.Button(label="Authorize on GitHub", url=url))
        await private_reply(
            interaction, "Authorize Lifeguard to open issues under your account.", view=view
        )
