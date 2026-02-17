from __future__ import annotations

from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from lifeguard.modules.voice_lobby.cog import VoiceLobbyCog


class RenameLobbyModal(discord.ui.Modal, title="Rename Lobby"):
    def __init__(self, cog: "VoiceLobbyCog", voice_channel_id: int) -> None:
        super().__init__()
        self.cog = cog
        self.voice_channel_id = voice_channel_id
        self.new_name = discord.ui.TextInput(
            label="Channel Name",
            max_length=100,
            placeholder="My Team Lobby",
        )
        self.add_item(self.new_name)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog.update_lobby_name(
            interaction,
            self.voice_channel_id,
            str(self.new_name.value),
        )


class UserLimitModal(discord.ui.Modal, title="Set User Limit"):
    def __init__(self, cog: "VoiceLobbyCog", voice_channel_id: int) -> None:
        super().__init__()
        self.cog = cog
        self.voice_channel_id = voice_channel_id
        self.user_limit = discord.ui.TextInput(
            label="User Limit (0-99)",
            max_length=2,
            placeholder="0",
        )
        self.add_item(self.user_limit)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        raw_value = str(self.user_limit.value).strip()
        if not raw_value.isdigit():
            await interaction.response.send_message(
                "User limit must be a number between 0 and 99.",
                ephemeral=True,
            )
            return

        limit = int(raw_value)
        await self.cog.update_lobby_user_limit(interaction, self.voice_channel_id, limit)


class LobbyConfigView(discord.ui.View):
    """Owner-only controls for a temporary voice lobby."""

    def __init__(self, cog: "VoiceLobbyCog", voice_channel_id: int, owner_id: int) -> None:
        super().__init__(timeout=1800)
        self.cog = cog
        self.voice_channel_id = voice_channel_id
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True

        await interaction.response.send_message(
            "Only the lobby owner can use these controls.",
            ephemeral=True,
        )
        return False

    @discord.ui.button(label="Rename", style=discord.ButtonStyle.primary, emoji="✏️")
    async def rename_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.send_modal(RenameLobbyModal(self.cog, self.voice_channel_id))

    @discord.ui.button(label="Set Limit", style=discord.ButtonStyle.secondary, emoji="👥")
    async def set_limit_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.send_modal(UserLimitModal(self.cog, self.voice_channel_id))

    @discord.ui.button(label="Unlock", style=discord.ButtonStyle.secondary, emoji="🔓")
    async def unlock_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self.cog.update_lobby_user_limit(interaction, self.voice_channel_id, 0)

    @discord.ui.button(label="Close Lobby", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self.cog.close_lobby(interaction, self.voice_channel_id)
