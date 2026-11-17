"""Discord writes, including the unarchive/write/restore rule."""

from contextlib import asynccontextmanager, suppress

import discord

from .render import comment_embed, is_bot, item_kind, item_state, post_embed, truncate
from .tags import resolve_tags


class DiscordSink:
    def __init__(self, bot, store):
        self.bot, self.store = bot, store

    async def channel(self, channel_id):
        return self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)

    @asynccontextmanager
    async def writing(self, post, *, archived=None, locked=False):
        thread = await self.channel(post["thread_id"])
        if thread.archived:
            await thread.edit(archived=False)
        try:
            yield thread
        finally:
            close = post["state"] != "Open" if archived is None else archived
            await thread.edit(archived=close, locked=locked or thread.locked)

    async def upsert_post(self, link, item):
        guild, repo, number = link["guild_id"], link["repo"], item["number"]
        post = await self.store.post(guild, repo, number)
        forum = await self.channel(link["forum_id"])
        overrides = {
            row["label"]: row["tag_id"]
            for row in await self.store.all(
                "SELECT * FROM label_tags WHERE forum_id=?", (forum.id,)
            )
        }
        state, kind = item_state(item), item_kind(item)
        tags = resolve_tags(kind, state, item.get("labels", []), forum.available_tags, overrides)
        title = truncate(f"#{number} {item['title']}", 100)
        embed = post_embed(item)
        if post:
            post["state"] = state
            async with self.writing(post) as thread:
                await thread.edit(name=title, applied_tags=tags)
                await thread.get_partial_message(post["starter_msg_id"]).edit(
                    embed=embed, allowed_mentions=discord.AllowedMentions.none()
                )
        else:
            created = await forum.create_thread(
                name=title,
                embed=embed,
                applied_tags=tags,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            post = dict(
                guild_id=guild,
                repo=repo,
                number=number,
                kind=kind,
                thread_id=created.thread.id,
                starter_msg_id=created.message.id,
                state=state,
            )
            # Persist before archiving so a retry cannot create a second thread.
            await self.store.put("posts", **post)
            if state != "Open":
                await created.thread.edit(archived=True)
        await self.store.put("posts", **post)
        return post

    async def comment(self, link, item, comment, kind, action):
        guild, repo = link["guild_id"], link["repo"]
        existing = await self.store.comment(guild, repo, kind, comment["id"])
        if action in {"created", "submitted"} and existing:
            return
        post = await self.store.post(guild, repo, item["number"])
        if not post or (action == "deleted" and not existing):
            return
        modes = {
            r["login"]: r["mode"]
            for r in await self.store.all("SELECT * FROM bot_logins WHERE guild_id=?", (guild,))
        }
        collapsed = is_bot(comment.get("user") or {}, modes)
        async with self.writing(post) as thread:
            if action == "deleted":
                with suppress(discord.NotFound):
                    await thread.get_partial_message(existing["message_id"]).delete()
                await self.store.execute(
                    "DELETE FROM comments WHERE guild_id=? AND repo=? "
                    "AND gh_kind=? AND gh_comment_id=?",
                    (guild, repo, kind, comment["id"]),
                )
                return
            embed = comment_embed(comment, collapsed)
            if existing:
                message = thread.get_partial_message(existing["message_id"])
                try:
                    await message.edit(embed=embed, allowed_mentions=discord.AllowedMentions.none())
                except discord.NotFound:
                    message = await thread.send(
                        embed=embed, allowed_mentions=discord.AllowedMentions.none()
                    )
            else:
                message = await thread.send(
                    embed=embed, allowed_mentions=discord.AllowedMentions.none()
                )
            await self.store.put(
                "comments",
                guild_id=guild,
                repo=repo,
                number=item["number"],
                gh_comment_id=comment["id"],
                gh_kind=kind,
                gh_author_id=(comment.get("user") or {}).get("id"),
                thread_id=thread.id,
                message_id=message.id,
                collapsed=int(collapsed),
            )

    async def notice(self, link, item, text, *, locked=False, archived=None):
        post = await self.store.post(link["guild_id"], link["repo"], item["number"])
        if not post:
            post = await self.upsert_post(link, item)
        async with self.writing(post, archived=archived, locked=locked) as thread:
            await thread.send(
                embed=discord.Embed(description=text),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        if locked or archived:
            post["state"] = "Deleted" if locked else "Transferred"
            await self.store.put("posts", **post)
