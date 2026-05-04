from __future__ import annotations

from collections.abc import Awaitable, Callable

import discord
from discord.ext import commands

from lifeguard.features.adapters import CogBackedConfigAdapter
from lifeguard.modules.content_review.cog import ContentReviewCog


class ContentReviewConfigAdapter(CogBackedConfigAdapter[ContentReviewCog]):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(
            bot,
            cog_name="ContentReviewCog",
            missing_cog_message="ContentReviewCog is not loaded",
        )

    async def show_menu(
        self,
        interaction: discord.Interaction,
        *,
        on_back_to_home: Callable[[discord.Interaction], Awaitable[None]],
    ) -> None:
        await self._require_cog().show_config_menu(
            interaction,
            disabled_view=None,
            on_back_to_home=on_back_to_home,
        )

    async def show_status(
        self,
        interaction: discord.Interaction,
        *,
        on_back_to_home: Callable[[discord.Interaction], Awaitable[None]],
    ) -> None:
        await self.show_menu(interaction, on_back_to_home=on_back_to_home)

    async def show_setup(
        self,
        interaction: discord.Interaction,
        *,
        on_back_to_home: Callable[[discord.Interaction], Awaitable[None]],
        use_send: bool = False,
    ) -> None:
        await self._require_cog().show_setup(
            interaction,
            on_back_to_home=on_back_to_home,
            use_send=use_send,
        )

    async def enable(
        self,
        interaction: discord.Interaction,
        *,
        on_back_to_home: Callable[[discord.Interaction], Awaitable[None]] | None = None,
        use_send: bool = False,
    ) -> None:
        if on_back_to_home is None:
            raise RuntimeError("Content Review setup requires a home callback")
        await self.show_setup(
            interaction,
            on_back_to_home=on_back_to_home,
            use_send=use_send,
        )

    async def disable(
        self,
        interaction: discord.Interaction,
        *,
        use_send: bool = False,
    ) -> None:
        await self._require_cog().disable_feature(interaction, use_send=use_send)
