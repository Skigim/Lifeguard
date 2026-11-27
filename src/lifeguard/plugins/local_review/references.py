"""Resolve references to Lifeguard messages without searching channel history."""

from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass

import discord

MESSAGE_LINK = re.compile(
    r"<?https://(?:(?:canary|ptb)\.)?discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)(?![\w/])>?",
    re.IGNORECASE,
)
QUOTE = re.compile(r"^[ \t]*>>>[ \t](?P<multiline>[\s\S]*)|(?:^[ \t]*>[ \t][^\n]*(?:\n|$))+", re.M)


@dataclass(frozen=True)
class Reference:
    kind: str
    content: str | None


class References:
    def __init__(self) -> None:
        self.sent: OrderedDict[int, discord.Message] = OrderedDict()

    def remember(self, message: discord.Message) -> None:
        self.sent[message.id] = message
        self.sent.move_to_end(message.id)
        if len(self.sent) > 128:
            self.sent.popitem(last=False)

    async def resolve(
        self, message: discord.Message, user_id: int, text: str
    ) -> tuple[Reference | None, str]:
        assert message.guild is not None
        quotes = [
            match["multiline"] or re.sub(r"^[ \t]*>[ \t]", "", match[0], flags=re.M)
            for match in QUOTE.finditer(text)
        ]
        authored = QUOTE.sub("", text)
        prompt = MESSAGE_LINK.sub("", authored).strip()
        if not prompt:
            return None, ""

        reference = message.reference
        if reference and reference.message_id and reference.guild_id in {None, message.guild.id}:
            if message.type is discord.MessageType.reply:
                original = reference.resolved
                if original is None and reference.channel_id == message.channel.id:
                    original = await self.original(
                        message, reference.channel_id, reference.message_id
                    )
                if isinstance(original, discord.Message) and original.author.id == user_id:
                    return Reference("reply", original.content), prompt
            if reference.type is discord.MessageReferenceType.forward and message.message_snapshots:
                original = await self.original(message, reference.channel_id, reference.message_id)
                if original is not None and original.author.id == user_id:
                    return Reference("forward", message.message_snapshots[0].content), prompt

        # Resolve only pasted Discord permalinks in the current guild.
        for link in list(MESSAGE_LINK.finditer(authored))[:3]:
            guild_id, channel_id, message_id = map(int, link.groups())
            if guild_id != message.guild.id:
                continue
            original = await self.original(message, channel_id, message_id)
            if original is not None and original.author.id == user_id:
                # A link in another channel doesn't make the original's text visible there.
                content = original.content if channel_id == message.channel.id else None
                return Reference("link", content), prompt

        for quote in quotes:
            normalized = " ".join(quote.split())
            if not normalized:
                continue
            candidates = [
                " ".join(sent.content.split())
                for sent in self.sent.values()
                if sent.guild is not None and sent.guild.id == message.guild.id
            ]
            if normalized in candidates or (
                len(normalized) >= 24 and sum(normalized in item for item in candidates) == 1
            ):
                return Reference("quote", quote.strip()), prompt
        return None, text

    async def original(
        self, message: discord.Message, channel_id: int, message_id: int
    ) -> discord.Message | None:
        assert message.guild is not None
        cached = self.sent.get(message_id)
        if channel_id == message.channel.id:
            channel = message.channel
        else:
            channel = message.guild.get_channel_or_thread(channel_id)
            if not isinstance(channel, discord.abc.Messageable):
                return None
            permissions = channel.permissions_for(message.author)
            if not (permissions.view_channel and permissions.read_message_history):
                return None
            if (
                isinstance(channel, discord.Thread)
                and channel.is_private()
                and not permissions.manage_threads
                and channel.get_member(message.author.id) is None
            ):
                return None
        if cached is not None and cached.channel.id == channel_id:
            return cached
        try:
            return await channel.fetch_message(message_id)
        except (discord.NotFound, discord.Forbidden):
            return None
