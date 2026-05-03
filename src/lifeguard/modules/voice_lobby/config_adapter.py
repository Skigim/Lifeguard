from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import cast

import discord
from discord.ext import commands

from lifeguard.modules.voice_lobby.cog import VoiceLobbyCog
from lifeguard.modules.voice_lobby.views.config_ui import VoiceLobbyConfigView


class VoiceLobbyConfigAdapter:
    def __init__(self, bot: commands.Bot) -> None:
        self._cog = cast(VoiceLobbyCog | None, bot.get_cog("VoiceLobbyCog"))
        self._on_back_to_home: Callable[[discord.Interaction], Awaitable[None]] | None = None

    def _require_cog(self) -> VoiceLobbyCog:
        if self._cog is None:
            raise RuntimeError("VoiceLobbyCog is not loaded")
        return self._cog

    def _require_on_back_to_home(
        self,
    ) -> Callable[[discord.Interaction], Awaitable[None]]:
        if self._on_back_to_home is None:
            raise RuntimeError("Voice Lobby config requires a home callback")
        return self._on_back_to_home

    def build_menu_view(self) -> VoiceLobbyConfigView:
        return VoiceLobbyConfigView(self, on_back_to_home=self._require_on_back_to_home())

    async def show_menu(
        self,
        interaction: discord.Interaction,
        *,
        on_back_to_home: Callable[[discord.Interaction], Awaitable[None]],
    ) -> None:
        self._on_back_to_home = on_back_to_home
        await self._require_cog().show_config_status(
            interaction,
            view=self.build_menu_view(),
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

    async def set_entry_channel(
        self,
        interaction: discord.Interaction,
        entry_channel: discord.VoiceChannel,
    ) -> None:
        await self._require_cog().set_entry_channel(
            interaction,
            entry_channel,
            view=self.build_menu_view(),
        )

    async def set_category(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel | None,
    ) -> None:
        await self._require_cog().set_category(
            interaction,
            category,
            view=self.build_menu_view(),
        )

    async def set_defaults(
        self,
        interaction: discord.Interaction,
        name_template: str,
        default_user_limit: int,
    ) -> None:
        await self._require_cog().set_defaults(
            interaction,
            name_template,
            str(default_user_limit),
        )

    async def add_creator_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
    ) -> None:
        await self._require_cog().add_creator_role(
            interaction,
            role,
            view=self.build_menu_view(),
        )

    async def remove_creator_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
    ) -> None:
        await self._require_cog().remove_creator_role(
            interaction,
            role,
            view=self.build_menu_view(),
        )

    async def clear_creator_roles(self, interaction: discord.Interaction) -> None:
        await self._require_cog().clear_creator_roles(
            interaction,
            view=self.build_menu_view(),
        )

    async def add_join_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
    ) -> None:
        await self._require_cog().add_join_role(
            interaction,
            role,
            view=self.build_menu_view(),
        )

    async def remove_join_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
    ) -> None:
        await self._require_cog().remove_join_role(
            interaction,
            role,
            view=self.build_menu_view(),
        )

    async def clear_join_roles(self, interaction: discord.Interaction) -> None:
        await self._require_cog().clear_join_roles(
            interaction,
            view=self.build_menu_view(),
        )