"""Discord writes, including the unarchive/write/restore rule."""

from contextlib import asynccontextmanager, suppress

import discord

from .render import (
    activity_text,
    comment_embed,
    is_bot,
    item_kind,
    item_state,
    post_embed,
    starter_embeds,
    truncate,
)
from .tags import resolve_tags


class DiscordSink:
    def __init__(self, bot, store):
        self.bot, self.store = bot, store

    async def channel(self, channel_id):
        return self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)

    async def update_starter(self, thread, post, base=None):
        if base is None:
            message = await thread.fetch_message(post["starter_msg_id"])
            base = message.embeds[0]
        rows = await self.store.all(
            "SELECT activity_text, activity_url FROM comments WHERE guild_id=? AND thread_id=? "
            "AND activity_text IS NOT NULL ORDER BY activity_at DESC, gh_comment_id DESC LIMIT 5",
            (post["guild_id"], post["thread_id"]),
        )
        await thread.get_partial_message(post["starter_msg_id"]).edit(
            embeds=starter_embeds(base, rows, post.get("latest_notice")),
            allowed_mentions=discord.AllowedMentions.none(),
        )

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
                await self.update_starter(thread, post, embed)
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
        post = await self.store.post(guild, repo, item["number"])
        if not post or post["state"] in {"Deleted", "Transferred"}:
            return
        modes = {
            r["login"]: r["mode"]
            for r in await self.store.all("SELECT * FROM bot_logins WHERE guild_id=?", (guild,))
        }
        collapsed = is_bot(comment.get("user") or {}, modes)
        async with self.writing(post) as thread:
            legacy_id = existing["message_id"] if existing else None
            if action == "deleted":
                if legacy_id:
                    with suppress(discord.NotFound):
                        await thread.get_partial_message(legacy_id).delete()
                await self.store.execute(
                    "DELETE FROM comments WHERE guild_id=? AND repo=? "
                    "AND gh_kind=? AND gh_comment_id=?",
                    (guild, repo, kind, comment["id"]),
                )
            elif not existing or action not in {"created", "submitted"}:
                if legacy_id:
                    try:
                        await thread.get_partial_message(legacy_id).edit(
                            embed=comment_embed(comment, collapsed),
                            allowed_mentions=discord.AllowedMentions.none(),
                        )
                    except discord.NotFound:
                        legacy_id = None
                await self.store.put(
                    "comments",
                    guild_id=guild,
                    repo=repo,
                    number=item["number"],
                    gh_comment_id=comment["id"],
                    gh_kind=kind,
                    gh_author_id=(comment.get("user") or {}).get("id"),
                    thread_id=thread.id,
                    message_id=legacy_id,
                    collapsed=int(collapsed),
                    activity_text=None if legacy_id else activity_text(comment, kind, collapsed),
                    activity_url=comment.get("html_url"),
                    activity_at=comment.get("created_at") or comment.get("submitted_at"),
                )
            await self.update_starter(thread, post)

    async def notice(self, link, item, text, *, locked=False, archived=None):
        post = await self.store.post(link["guild_id"], link["repo"], item["number"])
        if not post:
            post = await self.upsert_post(link, item)
        post["latest_notice"] = text
        async with self.writing(post, archived=archived, locked=locked) as thread:
            await self.update_starter(thread, post)
        if locked or archived:
            post["state"] = "Deleted" if locked else "Transferred"
        await self.store.put("posts", **post)
