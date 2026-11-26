"""Send Discord thread reviews to a connected agent and file the resulting issues."""

from __future__ import annotations

import asyncio
import re
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

from .process import LocalReview, ReviewError

if TYPE_CHECKING:
    from lifeguard.bot import LifeguardBot

REVIEW_REQUEST = re.compile(
    r"(?:(?:can|could|would)\s+you\s+)?(?:please\s+)?"
    r"(?:review|read|look\s+through)\s+(?:this|the)\s+"
    r"(?:discussion(?:\s+thread)?|thread)(?:\s*,\s*|\s+)and\s+"
    r"(?:add|create|file|open)\s+(?:(?:any|the|relevant|actionable|new|github)\s+)*issues?"
    r"(?:\s+(?:to|on|in)\s+github)?[.!?]?"
    r"(?:\s+repo:(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?))?[.!?]?",
    re.IGNORECASE,
)
MAX_MESSAGES = 80
MAX_CONTEXT_CHARS = 8000
REPO_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
REVIEW_DOCS = "https://github.com/Skigim/Lifeguard/blob/main/docs/features/local-review.md"


async def select_repo(store: Store, thread: discord.Thread, requested: str | None) -> str:
    guild_id = thread.guild.id
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

    if post := await store.one(
        "SELECT repo FROM posts JOIN repo_links USING (guild_id, repo) "
        "WHERE guild_id=? AND thread_id=?",
        (guild_id, thread.id),
    ):
        return post["repo"]
    links = await store.all(
        "SELECT repo FROM repo_links WHERE guild_id=? AND forum_id=? LIMIT 2",
        (guild_id, thread.parent_id),
    )
    if not links:
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
        self.guild_commands = app_commands.Group(
            name="lg", description="Connect an agent to Lifeguard", guild_only=True
        )
        self.guild_commands.command(name="hook", description="Show the local agent hook")(self.hook)
        self.guild_commands.command(name="setup", description="Set up your local review agent")(
            self.setup_agent
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
            "- `POST /v1/jobs/next` claims a review job.\n"
            "- `POST /v1/jobs/{id}/result` returns the proposed issues.\n"
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

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        user = self.bot.user
        if user is None or message.guild is None or message.author.bot or message.webhook_id:
            return
        mention = re.match(rf"<@!?{user.id}>[\s,]*", message.content)
        if mention is None:
            return
        match = REVIEW_REQUEST.fullmatch(message.content[mention.end() :].strip())
        if match is None:
            return
        guild_id = message.guild.id
        try:
            reviewer = self.bot.loader.require(LocalReview.name, guild_id)
        except ProcessDisabled:
            return
        if not isinstance(message.channel, discord.Thread):
            await self.reply(message, "Ask me to review from inside the discussion thread.")
            return
        if self.review_lock.locked():
            await self.reply(
                message, "An agent is already reviewing another thread. Try again shortly."
            )
            return
        async with self.review_lock:
            try:
                await self.review_thread(message, message.channel, reviewer, match["repo"])
            except ProcessDisabled:
                await self.reply(message, "Local review was disabled in this server.")
            except (ReviewError, RelinkRequired) as exc:
                await self.reply(message, str(exc))
            except discord.Forbidden:
                await self.reply(message, "I need permission to read this thread and its history.")
            except discord.HTTPException:
                await self.reply(message, "Discord could not complete the review request.")

    async def review_thread(
        self,
        message: discord.Message,
        thread: discord.Thread,
        reviewer: LocalReview,
        requested_repo: str | None,
    ) -> None:
        store, github = reviewer.github.store, reviewer.github.gh
        if await store.one("SELECT 1 FROM local_review_requests WHERE message_id=?", (message.id,)):
            return
        repo = await select_repo(store, thread, requested_repo)
        author_id = message.author.id
        if not await store.one("SELECT 1 FROM user_links WHERE discord_id=?", (author_id,)):
            raise ReviewError("Link your GitHub account from `/lg setup` first.")
        context, limited = await thread_context(thread, message)
        if not context:
            raise ReviewError("I found no discussion text before your request.")
        guild_id = thread.guild.id
        if self.bot.loader.require(LocalReview.name, guild_id) is not reviewer:
            raise ReviewError("Local review restarted. Send a new request to try again.")
        async with thread.typing():
            issues = await reviewer.review(guild_id, repo, thread.name, context, limited)
        scope = "\nI reviewed the most recent messages within the context limit." if limited else ""
        if not issues:
            await self.reply(message, "I found no actionable GitHub issues." + scope)
            return

        # Check enablement again after waiting for the agent.
        if self.bot.loader.require(LocalReview.name, guild_id) is not reviewer:
            raise ReviewError("Local review restarted. Send a new request to try again.")
        try:
            token = await github.user_token(author_id)
        except RelinkRequired as exc:
            raise ReviewError("Relink your GitHub account from `/lg setup`.") from exc
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise ReviewError("GitHub could not check your linked account.") from exc
        await select_repo(store, thread, repo)
        if not await store.execute(
            "INSERT OR IGNORE INTO local_review_requests VALUES (?)", (message.id,)
        ):
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
                "Then start the agent polling `POST /v1/jobs/next`.\n"
                "4. Click **Link GitHub**, then mention Lifeguard in a discussion thread.\n\n"
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
        view = discord.ui.View(timeout=600)
        url = await link_url(reviewer.github, interaction.user.id)
        view.add_item(discord.ui.Button(label="Authorize on GitHub", url=url))
        await private_reply(
            interaction, "Authorize Lifeguard to open issues under your account.", view=view
        )
