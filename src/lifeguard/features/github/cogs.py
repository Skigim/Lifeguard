"""Guild-gated administration, account linking, and explicit GitHub writes."""

from __future__ import annotations

import re
import secrets
import time
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands
from gidgethub import GitHubException

from lifeguard.core.loader import ProcessDisabled
from lifeguard.core.replies import REPLY_TTL, reply

from .gh import RelinkRequired
from .tags import REQUIRED_TAGS


class BridgeError(RuntimeError):
    pass


def require(bot, interaction):
    if interaction.guild_id is None:
        raise BridgeError("Use this command in a server.")
    return bot.loader.require("github", interaction.guild_id)


async def link_view(proc, user_id):
    state = secrets.token_urlsafe(32)
    await proc.store.put("oauth_states", state=state, discord_id=user_id, created_at=time.time())
    view = discord.ui.View(timeout=600)
    view.add_item(
        discord.ui.Button(
            label="Link GitHub", url=f"{proc.settings.public_url}/oauth/start?state={state}"
        )
    )
    return view


async def report(bot, interaction, error):
    error = getattr(error, "original", error)
    if isinstance(error, RelinkRequired):
        proc = require(bot, interaction)
        await reply(interaction, str(error), view=await link_view(proc, interaction.user.id))
    elif isinstance(error, ProcessDisabled):
        from lifeguard.bot import DISABLED_MESSAGE

        await reply(interaction, DISABLED_MESSAGE)
    elif isinstance(error, BridgeError):
        await reply(interaction, str(error))
    elif isinstance(error, GitHubException):
        if getattr(error, "status_code", None) in {403, 404}:
            await reply(interaction, "You don't have permission on this repository.")
        else:
            await reply(interaction, "GitHub could not complete that action. Please try again.")
    else:
        from lifeguard.bot import on_app_command_error

        await on_app_command_error(interaction, error)
    interaction.extras["github_error_handled"] = True


async def thread_post(proc, interaction):
    row = await proc.store.one(
        "SELECT * FROM posts WHERE guild_id=? AND thread_id=?",
        (interaction.guild_id, interaction.channel_id),
    )
    if not row or not await proc.store.one(
        "SELECT * FROM repo_links WHERE guild_id=? AND repo=?", (row["guild_id"], row["repo"])
    ):
        raise BridgeError("Use this command inside a bridged issue or PR thread.")
    return row


async def author_comment(proc, interaction, message_id):
    await thread_post(proc, interaction)
    row = await proc.store.one(
        "SELECT * FROM comments WHERE guild_id=? AND thread_id=? AND message_id=?",
        (interaction.guild_id, interaction.channel_id, message_id),
    )
    if not row or row["collapsed"]:
        raise BridgeError("This action is only available for mirrored human comments.")
    token = await proc.gh.user_token(interaction.user.id)
    user = await proc.store.one(
        "SELECT * FROM user_links WHERE discord_id=?", (interaction.user.id,)
    )
    if not user or user["gh_id"] != row["gh_author_id"]:
        raise BridgeError("Only the linked GitHub author can edit or delete this comment.")
    return row, token


@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
class BridgeAdmin(commands.GroupCog, group_name="bridge", group_description="Manage GitHub forums"):
    def __init__(self, bot):
        self.bot = bot

    async def interaction_check(self, interaction):
        if not interaction.permissions.manage_guild:
            raise BridgeError("Manage Server permission is required.")
        require(self.bot, interaction)
        return True

    async def cog_app_command_error(self, interaction, error):
        await report(self.bot, interaction, error)

    @app_commands.command(name="link-repo", description="Bridge a GitHub repository to a forum")
    async def link_repo(
        self, interaction: discord.Interaction, repo: str, forum: discord.ForumChannel
    ):
        proc = require(self.bot, interaction)
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
            raise BridgeError("Use owner/repo for the repository.")
        if forum.guild.id != interaction.guild_id:
            raise BridgeError("Choose a forum in this server.")
        perms = forum.permissions_for(interaction.guild.me)
        if not all(
            (
                perms.view_channel,
                perms.send_messages,
                perms.send_messages_in_threads,
                perms.manage_threads,
                perms.embed_links,
                perms.read_message_history,
            )
        ):
            raise BridgeError(
                "The bot needs View Channel, Create Posts, Send in Threads, "
                "Manage Threads, Embed Links and Read Message History here."
            )
        await interaction.response.defer(ephemeral=True)
        repo = repo.lower()
        installation = await proc.gh.get_repo_installation(repo)
        existing = await proc.store.one(
            "SELECT * FROM repo_links WHERE guild_id=? AND repo=?", (interaction.guild_id, repo)
        )
        if existing and existing["forum_id"] != forum.id:
            raise BridgeError("Unlink this repository before changing its forum.")
        names = {tag.name.casefold() for tag in forum.available_tags}
        missing = [name for name in REQUIRED_TAGS if name.casefold() not in names]
        if len(forum.available_tags) + len(missing) > 20:
            raise BridgeError("Make room for the Issue, PR, Open, Closed and Merged forum tags.")
        if missing:
            if not perms.manage_channels:
                raise BridgeError(
                    "The bot needs Manage Channels to create the required forum tags, "
                    "or an admin can create Issue, PR, Open, Closed and Merged first."
                )
            await forum.edit(
                available_tags=[
                    *forum.available_tags,
                    *[discord.ForumTag(name=name) for name in missing],
                ]
            )
        await proc.store.put(
            "repo_links",
            guild_id=interaction.guild_id,
            repo=repo,
            forum_id=forum.id,
            installation_id=installation["id"],
        )
        await reply(
            interaction,
            f"Linked `{repo}` to {forum.mention}. Use `/bridge backfill` for open items.",
        )

    @app_commands.command(
        name="unlink-repo", description="Stop mirroring a repository; keep history"
    )
    async def unlink_repo(self, interaction: discord.Interaction, repo: str):
        proc = require(self.bot, interaction)
        await proc.store.execute(
            "DELETE FROM repo_links WHERE guild_id=? AND repo=?",
            (interaction.guild_id, repo.lower()),
        )
        await reply(interaction, f"Unlinked `{repo}`. Discord history is retained.")

    @app_commands.command(description="List repositories bridged to this server")
    async def repos(self, interaction: discord.Interaction):
        proc = require(self.bot, interaction)
        rows = await proc.store.all(
            "SELECT * FROM repo_links WHERE guild_id=?", (interaction.guild_id,)
        )
        text = (
            "\n".join(f"`{r['repo']}` → <#{r['forum_id']}>" for r in rows)
            or "No linked repositories."
        )
        await reply(interaction, text[:1900])

    @app_commands.command(
        name="map-label", description="Map a GitHub label to an existing forum tag"
    )
    async def map_label(
        self, interaction: discord.Interaction, forum: discord.ForumChannel, label: str, tag: str
    ):
        proc = require(self.bot, interaction)
        if not await proc.store.one(
            "SELECT * FROM repo_links WHERE guild_id=? AND forum_id=?",
            (interaction.guild_id, forum.id),
        ):
            raise BridgeError("That forum is not bridged in this server.")
        match = next(
            (
                t
                for t in forum.available_tags
                if t.name.casefold() == tag.casefold() or str(t.id) == tag
            ),
            None,
        )
        if not match:
            raise BridgeError("Choose an existing tag name or ID.")
        await proc.store.put("label_tags", forum_id=forum.id, label=label, tag_id=match.id)
        await reply(interaction, "Label mapping saved.")

    @app_commands.command(description="Create or refresh posts for all open issues and PRs")
    @app_commands.describe(repo="Linked repository. Optional if this server has only one.")
    async def backfill(self, interaction: discord.Interaction, repo: str | None = None):
        proc = require(self.bot, interaction)
        if repo is None:
            links = await proc.store.all(
                "SELECT * FROM repo_links WHERE guild_id=? LIMIT 2", (interaction.guild_id,)
            )
            if not links:
                raise BridgeError("Link a repository first with `/bridge link-repo`.")
            if len(links) > 1:
                raise BridgeError("Choose a linked repository in the `repo` field.")
            link = links[0]
        else:
            link = await proc.store.one(
                "SELECT * FROM repo_links WHERE guild_id=? AND repo=?",
                (interaction.guild_id, repo.strip().lower()),
            )
            if not link:
                raise BridgeError("Link this repository first.")
        await interaction.response.defer(ephemeral=True)
        count = await proc.backfill(link)
        await reply(interaction, f"Synced {count} open items.")

    @backfill.autocomplete("repo")
    async def backfill_repos(self, interaction: discord.Interaction, current: str):
        if interaction.guild_id is None or not interaction.permissions.manage_guild:
            return []
        try:
            proc = require(self.bot, interaction)
        except ProcessDisabled:
            return []
        rows = await proc.store.all(
            "SELECT repo FROM repo_links WHERE guild_id=? AND instr(repo, ?) > 0 "
            "ORDER BY repo LIMIT 25",
            (interaction.guild_id, current.lower()),
        )
        return [app_commands.Choice(name=row["repo"], value=row["repo"]) for row in rows]

    login_group = app_commands.Group(name="bot-login", description="Override bot comment collapse")

    @login_group.command(name="add", description="Always collapse or never collapse a login")
    async def add_login(
        self,
        interaction: discord.Interaction,
        login: str,
        mode: Literal["collapse", "human"] = "collapse",
    ):
        proc = require(self.bot, interaction)
        await proc.store.put(
            "bot_logins", guild_id=interaction.guild_id, login=login.casefold(), mode=mode
        )
        await reply(interaction, "Bot login override saved.")

    @login_group.command(name="remove", description="Remove a login override")
    async def remove_login(self, interaction: discord.Interaction, login: str):
        proc = require(self.bot, interaction)
        await proc.store.execute(
            "DELETE FROM bot_logins WHERE guild_id=? AND login=?",
            (interaction.guild_id, login.casefold()),
        )
        await reply(interaction, "Bot login override removed.")


@app_commands.guild_only()
class GitHubAccount(
    commands.GroupCog, group_name="github", group_description="Your GitHub account"
):
    def __init__(self, bot):
        self.bot = bot

    async def cog_app_command_error(self, interaction, error):
        await report(self.bot, interaction, error)

    @app_commands.command(description="Link your GitHub identity")
    async def link(self, interaction: discord.Interaction):
        proc = require(self.bot, interaction)
        await reply(
            interaction,
            "Authorize your GitHub account (link expires in 10 minutes).",
            view=await link_view(proc, interaction.user.id),
        )

    @app_commands.command(description="Revoke and remove your GitHub authorization")
    async def unlink(self, interaction: discord.Interaction):
        proc = require(self.bot, interaction)
        await interaction.response.defer(ephemeral=True)
        await proc.gh.unlink(interaction.user.id)
        await reply(interaction, "Your GitHub account has been unlinked.")

    @app_commands.command(description="Show your linked GitHub account")
    async def whoami(self, interaction: discord.Interaction):
        proc = require(self.bot, interaction)
        await interaction.response.defer(ephemeral=True)
        await proc.gh.user_token(interaction.user.id)
        row = await proc.store.one(
            "SELECT gh_login FROM user_links WHERE discord_id=?", (interaction.user.id,)
        )
        await reply(interaction, f"Linked as **{row['gh_login']}**.")


class CommentModal(discord.ui.Modal):
    def __init__(self, bot, message_id=None, body=""):
        super().__init__(title="Edit on GitHub" if message_id else "Comment on GitHub")
        self.bot, self.message_id = bot, message_id
        self.body = discord.ui.TextInput(
            label="Comment", style=discord.TextStyle.paragraph, max_length=4000, default=body
        )
        self.add_item(self.body)

    async def on_error(self, interaction, error):
        await report(self.bot, interaction, error)

    async def on_submit(self, interaction):
        await interaction.response.defer(ephemeral=True)
        proc = require(self.bot, interaction)
        post = await thread_post(proc, interaction)
        async with proc.locks[(post["repo"], post["number"])]:
            if self.message_id:
                row, token = await author_comment(proc, interaction, self.message_id)
                comment = await proc.gh.edit_comment(row, self.body.value, token)
                kind, action = row["gh_kind"], "edited"
            else:
                token = await proc.gh.user_token(interaction.user.id)
                comment = await proc.gh.create_comment(
                    post["repo"], post["number"], self.body.value, token
                )
                kind, action = "issue_comment", "created"
            await proc.sink.comment(post, post, comment, kind, action)
        await reply(interaction, "Saved on GitHub.")


class EditView(discord.ui.View):
    def __init__(self, bot, user_id, message_id, body):
        super().__init__(timeout=300)
        self.bot, self.user_id, self.message_id, self.body = bot, user_id, message_id, body

    @discord.ui.button(label="Open editor", style=discord.ButtonStyle.primary)
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return
        await interaction.response.send_modal(CommentModal(self.bot, self.message_id, self.body))


class DeleteView(discord.ui.View):
    def __init__(self, bot, user_id, message_id):
        super().__init__(timeout=60)
        self.bot, self.user_id, self.message_id = bot, user_id, message_id
        self.used = False

    async def on_error(self, interaction, error, item):
        await report(self.bot, interaction, error)

    @discord.ui.button(label="Yes, delete", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id or self.used:
            await reply(interaction, "This confirmation is no longer available.")
            return
        self.used = True
        await interaction.response.defer(ephemeral=True)
        proc = require(self.bot, interaction)
        post = await thread_post(proc, interaction)
        async with proc.locks[(post["repo"], post["number"])]:
            row, token = await author_comment(proc, interaction, self.message_id)
            await proc.gh.delete_comment(row, token)
            await proc.sink.comment(
                post, post, {"id": row["gh_comment_id"]}, row["gh_kind"], "deleted"
            )
        await reply(interaction, "Deleted on GitHub.")
        self.stop()

    @discord.ui.button(label="Cancel")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == self.user_id:
            self.used = True
            await interaction.response.edit_message(
                content="Cancelled.", view=None, delete_after=REPLY_TTL
            )
            self.stop()


class ThreadActions(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.menus = [
            app_commands.ContextMenu(name="Edit on GitHub", callback=self.edit),
            app_commands.ContextMenu(name="Delete on GitHub", callback=self.delete),
        ]
        for menu in self.menus:
            menu.guild_only = True
            menu.error(self.menu_error)
            bot.tree.add_command(menu)

    async def cog_unload(self):
        for menu in self.menus:
            self.bot.tree.remove_command(menu.name, type=menu.type)

    async def menu_error(self, interaction, error):
        await report(self.bot, interaction, error)

    async def cog_app_command_error(self, interaction, error):
        await report(self.bot, interaction, error)

    @app_commands.command(description="Write a comment using your linked GitHub account")
    @app_commands.guild_only()
    async def comment(self, interaction: discord.Interaction):
        proc = require(self.bot, interaction)
        await thread_post(proc, interaction)
        await interaction.response.send_modal(CommentModal(self.bot))

    @app_commands.command(description="Close this issue or PR on GitHub")
    @app_commands.guild_only()
    async def close(
        self,
        interaction: discord.Interaction,
        reason: Literal["completed", "not_planned"] = "completed",
    ):
        await self.state(interaction, "closed", reason)

    @app_commands.command(description="Reopen this issue or PR on GitHub")
    @app_commands.guild_only()
    async def reopen(self, interaction: discord.Interaction):
        await self.state(interaction, "open")

    async def state(self, interaction, state, reason=None):
        proc = require(self.bot, interaction)
        await interaction.response.defer(ephemeral=True)
        post = await thread_post(proc, interaction)
        token = await proc.gh.user_token(interaction.user.id)
        async with proc.locks[(post["repo"], post["number"])]:
            await proc.gh.set_state(
                post["repo"],
                post["number"],
                state,
                token,
                reason if post["kind"] == "Issue" else None,
            )
        await reply(interaction, "Updated on GitHub. The webhook will sync this thread.")

    async def edit(self, interaction: discord.Interaction, message: discord.Message):
        proc = require(self.bot, interaction)
        await interaction.response.defer(ephemeral=True)
        row, token = await author_comment(proc, interaction, message.id)
        comment = await proc.gh.get_comment(row, token)
        body = comment.get("body") or ""
        if len(body) > 4000:
            raise BridgeError("This comment exceeds the Discord editor limit. Edit it on GitHub.")
        await reply(
            interaction,
            "Edit your GitHub comment:",
            view=EditView(self.bot, interaction.user.id, message.id, body),
        )

    async def delete(self, interaction: discord.Interaction, message: discord.Message):
        proc = require(self.bot, interaction)
        await interaction.response.defer(ephemeral=True)
        row, token = await author_comment(proc, interaction, message.id)
        if row["gh_kind"] == "review":
            raise BridgeError(
                "GitHub only allows deleting pending reviews. "
                "Submitted reviews cannot be deleted through this action."
            )
        await reply(
            interaction,
            "Delete this comment on GitHub? This cannot be undone.",
            view=DeleteView(self.bot, interaction.user.id, message.id),
        )


async def setup(bot):
    await bot.add_cog(BridgeAdmin(bot))
    await bot.add_cog(GitHubAccount(bot))
    await bot.add_cog(ThreadActions(bot))
