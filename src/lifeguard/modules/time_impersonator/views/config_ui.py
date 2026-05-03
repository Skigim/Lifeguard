from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from lifeguard.modules.time_impersonator.config_adapter import (
        TimeImpersonatorConfigAdapter,
    )


class TimeImpersonatorConfigView(discord.ui.View):
    """Config sub-menu for the Time Impersonator feature."""

    def __init__(
        self,
        adapter: "TimeImpersonatorConfigAdapter",
        *,
        on_back_to_home: Callable[[discord.Interaction], Awaitable[None]],
    ) -> None:
        super().__init__(timeout=120)
        self._adapter = adapter
        self._on_back_to_home = on_back_to_home

    @discord.ui.button(
        label="Status", style=discord.ButtonStyle.secondary, emoji="📋", row=0
    )
    async def status_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._adapter.show_status(
            interaction,
            on_back_to_home=self._on_back_to_home,
        )

    @discord.ui.button(
        label="Enable", style=discord.ButtonStyle.success, emoji="✅", row=0
    )
    async def enable_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._adapter.enable(
            interaction,
            on_back_to_home=self._on_back_to_home,
        )

    @discord.ui.button(
        label="Disable", style=discord.ButtonStyle.danger, emoji="❌", row=0
    )
    async def disable_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._adapter.disable(interaction)

    @discord.ui.button(
        label="Back", style=discord.ButtonStyle.secondary, emoji="↩️", row=1
    )
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._on_back_to_home(interaction)