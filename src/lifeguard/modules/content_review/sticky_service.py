"""Sticky submit-message lifecycle helpers for Content Review."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import discord

from lifeguard.modules.content_review import repo
from lifeguard.modules.content_review.config import ContentReviewConfig

if TYPE_CHECKING:
    from google.cloud.firestore import Client as FirestoreClient

LOGGER = logging.getLogger(__name__)


class SubmitButtonView(discord.ui.View):
    """Persistent view with Submit Content button for sticky message."""

    @staticmethod
    def _resolved_emoji(
        emoji: str | None,
    ) -> str | discord.PartialEmoji | None:
        """Resolve configured emoji into a valid Discord button emoji value."""
        if not emoji:
            return None

        raw = emoji.strip()
        if not raw:
            return None

        if raw.startswith("<") or raw.endswith(">"):
            if not re.fullmatch(r"<a?:[A-Za-z0-9_]{2,32}:\d+>", raw):
                LOGGER.warning("Ignoring invalid sticky button emoji value: %r", emoji)
                return None
            parsed = discord.PartialEmoji.from_str(raw)
            if parsed.id is not None:
                return parsed
            LOGGER.warning("Ignoring invalid sticky button emoji value: %r", emoji)
            return None

        parsed = discord.PartialEmoji.from_str(raw)
        if parsed.id is not None:
            return parsed

        if "<" in raw or ">" in raw:
            LOGGER.warning("Ignoring invalid sticky button emoji value: %r", emoji)
            return None

        if all(ch.isalnum() or ch.isspace() for ch in raw):
            LOGGER.warning("Ignoring invalid sticky button emoji value: %r", emoji)
            return None

        if len(raw) > 10:
            LOGGER.warning("Ignoring invalid sticky button emoji value: %r", emoji)
            return None

        return raw

    def __init__(self, label: str = "Submit Content", emoji: str = "📝") -> None:
        super().__init__(timeout=None)
        resolved_emoji = self._resolved_emoji(emoji)
        button = discord.ui.Button(
            label=label,
            style=discord.ButtonStyle.primary,
            custom_id="content_review:submit_content",
            emoji=resolved_emoji,
        )
        button.callback = self._button_callback
        self.add_item(button)

    async def _button_callback(self, interaction: discord.Interaction) -> None:
        pass


def build_sticky_embed(config: ContentReviewConfig) -> discord.Embed:
    """Build the sticky submit-button embed from config."""
    embed = discord.Embed(
        title=config.sticky_title,
        description=config.sticky_description,
        color=discord.Color.blue(),
    )
    embed.add_field(
        name="📋 How it works",
        value=(
            f"1. Click **{config.sticky_button_label}** below\n"
            "2. Fill out the form with your content details\n"
            "3. A private ticket will be created for your review\n"
            "4. Reviewers will provide feedback in your ticket"
        ),
        inline=False,
    )
    embed.set_footer(
        text="⚠️ By submitting, you agree to receive constructive feedback on your content."
    )
    return embed


async def resolve_submission_text_channel(
    guild: discord.Guild, config: ContentReviewConfig
) -> discord.TextChannel | None:
    """Resolve configured submission channel using cache first, then API."""
    if not config.submission_channel_id:
        return None

    channel = guild.get_channel(config.submission_channel_id)
    if channel is None:
        try:
            channel = await guild.fetch_channel(config.submission_channel_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None

    if isinstance(channel, discord.TextChannel):
        return channel
    return None


async def post_sticky_message(
    channel: discord.TextChannel, config: ContentReviewConfig
) -> discord.Message:
    """Post the sticky submit message and return it."""
    sticky_embed = build_sticky_embed(config)
    submit_button_view = SubmitButtonView(
        label=config.sticky_button_label,
        emoji=config.sticky_button_emoji,
    )
    return await channel.send(embed=sticky_embed, view=submit_button_view)


async def try_delete_sticky(guild: discord.Guild, config: ContentReviewConfig) -> None:
    """Attempt to delete the sticky submit-button message, ignoring errors."""
    if not config.sticky_message_id:
        return
    try:
        channel = await resolve_submission_text_channel(guild, config)
        if not channel:
            return
        msg = await channel.fetch_message(config.sticky_message_id)
        await msg.delete()
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        pass


async def _try_update_sticky(guild: discord.Guild, config: ContentReviewConfig) -> bool:
    """Attempt to edit the live sticky message with current config."""
    if not config.sticky_message_id:
        return False
    try:
        channel = await resolve_submission_text_channel(guild, config)
        if not channel:
            return False

        msg = await channel.fetch_message(config.sticky_message_id)
        sticky_embed = build_sticky_embed(config)
        submit_button_view = SubmitButtonView(
            label=config.sticky_button_label,
            emoji=config.sticky_button_emoji,
        )
        await msg.edit(embed=sticky_embed, view=submit_button_view)
        return True
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return False


async def sync_sticky_message(
    firestore: FirestoreClient,
    guild: discord.Guild,
    config: ContentReviewConfig,
) -> str:
    """Sync sticky message after config changes.

    Returns one of: "updated", "reposted", "failed".
    """
    if await _try_update_sticky(guild, config):
        return "updated"

    channel = await resolve_submission_text_channel(guild, config)
    if not channel:
        return "failed"

    try:
        sticky_msg = await post_sticky_message(channel, config)
        config.sticky_message_id = sticky_msg.id
        repo.save_config(firestore, config)
        return "reposted"
    except (discord.Forbidden, discord.HTTPException):
        return "failed"
