from __future__ import annotations

import discord
from discord.ext import commands

from lifeguard.features.adapters import StatusMenuConfigAdapter
from lifeguard.modules.voice_lobby.cog import VoiceLobbyCog
from lifeguard.modules.voice_lobby.views.config_ui import VoiceLobbyConfigView


class VoiceLobbyConfigAdapter(
    StatusMenuConfigAdapter[VoiceLobbyCog, VoiceLobbyConfigView]
):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(
            bot,
            cog_name="VoiceLobbyCog",
            missing_cog_message="VoiceLobbyCog is not loaded",
            missing_callback_message="Voice Lobby config requires a home callback",
        )

    def build_menu_view(self) -> VoiceLobbyConfigView:
        return VoiceLobbyConfigView(
            self,
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
