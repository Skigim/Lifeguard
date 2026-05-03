from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import cast

import discord
from discord.ext import commands

from lifeguard.modules.time_impersonator.cog import TimeImpersonatorCog
from lifeguard.modules.time_impersonator.views.config_ui import (
    TimeImpersonatorConfigView,
)


class TimeImpersonatorConfigAdapter:
    def __init__(self, bot: commands.Bot) -> None:
        self._cog = cast(TimeImpersonatorCog | None, bot.get_cog("TimeImpersonatorCog"))
        self._on_back_to_home: Callable[[discord.Interaction], Awaitable[None]] | None = None

    def _require_cog(self) -> TimeImpersonatorCog:
        if self._cog is None:
            raise RuntimeError("TimeImpersonatorCog is not loaded")
        return self._cog

    def _require_on_back_to_home(
        self,
    ) -> Callable[[discord.Interaction], Awaitable[None]]:
        if self._on_back_to_home is None:
            raise RuntimeError("Time Impersonator config requires a home callback")
        return self._on_back_to_home

    async def show_menu(
        self,
        interaction: discord.Interaction,
        *,
        on_back_to_home: Callable[[discord.Interaction], Awaitable[None]],
    ) -> None:
        self._on_back_to_home = on_back_to_home
        await self._require_cog().show_config_status(
            interaction,
            view=TimeImpersonatorConfigView(self, on_back_to_home=on_back_to_home),
        )

    async def show_status(
        self,
        interaction: discord.Interaction,
        *,
        on_back_to_home: Callable[[discord.Interaction], Awaitable[None]],
    ) -> None:
        await self.show_menu(interaction, on_back_to_home=on_back_to_home)

    async def enable(
        self,
        interaction: discord.Interaction,
        *,
        on_back_to_home: Callable[[discord.Interaction], Awaitable[None]] | None = None,
        use_send: bool = False,
    ) -> None:
        if on_back_to_home is not None:
            self._on_back_to_home = on_back_to_home
        await self._require_cog().enable_feature(interaction, use_send=use_send)

    async def disable(
        self,
        interaction: discord.Interaction,
        *,
        use_send: bool = False,
    ) -> None:
        await self._require_cog().disable_feature(interaction, use_send=use_send)

    async def show_menu_panel(self, interaction: discord.Interaction) -> None:
        await self.show_menu(
            interaction,
            on_back_to_home=self._require_on_back_to_home(),
        )