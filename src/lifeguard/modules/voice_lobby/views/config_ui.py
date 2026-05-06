from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from lifeguard.modules.voice_lobby.config_adapter import VoiceLobbyConfigAdapter
    from lifeguard.modules.voice_lobby.cog import VoiceLobbyCog


class RenameLobbyModal(discord.ui.Modal, title="Rename Lobby"):
    def __init__(self, cog: "VoiceLobbyCog", voice_channel_id: int) -> None:
        super().__init__()
        self.cog = cog
        self.voice_channel_id = voice_channel_id
        self.new_name: discord.ui.TextInput = discord.ui.TextInput(
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
        self.user_limit: discord.ui.TextInput = discord.ui.TextInput(
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
        await self.cog.update_lobby_user_limit(
            interaction, self.voice_channel_id, limit
        )


class LobbyConfigView(discord.ui.View):
    """Owner-only controls for a temporary voice lobby."""

    def __init__(
        self, cog: "VoiceLobbyCog", voice_channel_id: int, owner_id: int
    ) -> None:
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
        await interaction.response.send_modal(
            RenameLobbyModal(self.cog, self.voice_channel_id)
        )

    @discord.ui.button(
        label="Set Limit", style=discord.ButtonStyle.secondary, emoji="👥"
    )
    async def set_limit_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.send_modal(
            UserLimitModal(self.cog, self.voice_channel_id)
        )

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


class VoiceLobbyConfigView(discord.ui.View):
    """Config menu for Voice Lobby feature defaults."""

    def __init__(
        self,
        adapter: "VoiceLobbyConfigAdapter",
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
        label="Entry Channel", style=discord.ButtonStyle.secondary, emoji="🎙️", row=0
    )
    async def entry_channel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Select the entry voice channel:",
            embed=None,
            view=AssignVoiceEntryChannelView(self._adapter),
        )

    @discord.ui.button(
        label="Lobby Category", style=discord.ButtonStyle.secondary, emoji="🗂️", row=0
    )
    async def lobby_category_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Select the category for temporary lobbies, or use entry-channel category:",
            embed=None,
            view=AssignVoiceLobbyCategoryView(self._adapter),
        )

    @discord.ui.button(
        label="Defaults", style=discord.ButtonStyle.primary, emoji="⚙️", row=0
    )
    async def defaults_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(VoiceLobbyDefaultsModal(self._adapter))

    @discord.ui.button(
        label="Create Roles", style=discord.ButtonStyle.secondary, emoji="➕", row=1
    )
    async def create_roles_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Configure roles allowed to create lobbies:",
            embed=None,
            view=VoiceLobbyCreateRolesView(self._adapter),
        )

    @discord.ui.button(
        label="Join Roles", style=discord.ButtonStyle.secondary, emoji="👥", row=1
    )
    async def join_roles_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Configure roles allowed to join lobbies:",
            embed=None,
            view=VoiceLobbyJoinRolesView(self._adapter),
        )

    @discord.ui.button(
        label="Disable", style=discord.ButtonStyle.danger, emoji="❌", row=1
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


class AssignVoiceEntryChannelView(discord.ui.View):
    def __init__(self, adapter: "VoiceLobbyConfigAdapter") -> None:
        super().__init__(timeout=60)
        self._adapter = adapter

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        placeholder="Select an entry voice channel...",
        channel_types=[discord.ChannelType.voice],
        min_values=1,
        max_values=1,
    )
    async def channel_select(
        self, interaction: discord.Interaction, select: discord.ui.ChannelSelect
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message(
                "This must be used in a guild.", ephemeral=True
            )
            return

        selected_channel = select.values[0]
        channel = interaction.guild.get_channel(selected_channel.id)
        if not isinstance(channel, discord.VoiceChannel):
            await interaction.response.send_message(
                "Please select a voice channel.", ephemeral=True
            )
            return

        await self._adapter.set_entry_channel(interaction, channel)

    @discord.ui.button(
        label="Back", style=discord.ButtonStyle.secondary, emoji="↩️", row=1
    )
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._adapter.show_menu_panel(interaction)


class AssignVoiceLobbyCategoryView(discord.ui.View):
    def __init__(self, adapter: "VoiceLobbyConfigAdapter") -> None:
        super().__init__(timeout=60)
        self._adapter = adapter

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        placeholder="Select a category...",
        channel_types=[discord.ChannelType.category],
        min_values=1,
        max_values=1,
    )
    async def category_select(
        self, interaction: discord.Interaction, select: discord.ui.ChannelSelect
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message(
                "This must be used in a guild.", ephemeral=True
            )
            return

        selected_channel = select.values[0]
        category = interaction.guild.get_channel(selected_channel.id)
        if not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message(
                "Please select a valid category.", ephemeral=True
            )
            return

        await self._adapter.set_category(interaction, category)

    @discord.ui.button(
        label="Use Entry Category",
        style=discord.ButtonStyle.secondary,
        emoji="📍",
        row=1,
    )
    async def use_entry_category_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._adapter.set_category(interaction, None)

    @discord.ui.button(
        label="Back", style=discord.ButtonStyle.secondary, emoji="↩️", row=1
    )
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._adapter.show_menu_panel(interaction)


class VoiceLobbyDefaultsModal(discord.ui.Modal, title="Voice Lobby Defaults"):
    name_template: discord.ui.TextInput = discord.ui.TextInput(
        label="Name Template",
        placeholder="Lobby - {owner}",
        required=False,
        max_length=100,
    )
    default_user_limit: discord.ui.TextInput = discord.ui.TextInput(
        label="Default User Limit (0-99)",
        placeholder="0",
        default="0",
        max_length=2,
    )

    def __init__(self, adapter: "VoiceLobbyConfigAdapter") -> None:
        super().__init__()
        self._adapter = adapter

    async def on_submit(self, interaction: discord.Interaction) -> None:
        template = self.name_template.value.strip() or "Lobby - {owner}"
        raw_limit = self.default_user_limit.value.strip() or "0"
        if not raw_limit.isdigit():
            await interaction.response.send_message(
                "Default user limit must be a number between 0 and 99.",
                ephemeral=True,
            )
            return

        user_limit = int(raw_limit)
        if user_limit < 0 or user_limit > 99:
            await interaction.response.send_message(
                "Default user limit must be a number between 0 and 99.",
                ephemeral=True,
            )
            return

        await self._adapter.set_defaults(interaction, template, user_limit)


class VoiceLobbyCreateRolesView(discord.ui.View):
    def __init__(self, adapter: "VoiceLobbyConfigAdapter") -> None:
        super().__init__(timeout=60)
        self._adapter = adapter

    @discord.ui.button(
        label="Add Role", style=discord.ButtonStyle.success, emoji="➕", row=0
    )
    async def add_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Select a role to allow lobby creation:",
            embed=None,
            view=AddVoiceCreateRoleView(self._adapter),
        )

    @discord.ui.button(
        label="Remove Role", style=discord.ButtonStyle.secondary, emoji="➖", row=0
    )
    async def remove_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Select a role to remove from lobby creators:",
            embed=None,
            view=RemoveVoiceCreateRoleView(self._adapter),
        )

    @discord.ui.button(
        label="Clear Roles", style=discord.ButtonStyle.danger, emoji="🗑️", row=0
    )
    async def clear_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._adapter.clear_creator_roles(interaction)

    @discord.ui.button(
        label="Back", style=discord.ButtonStyle.secondary, emoji="↩️", row=1
    )
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._adapter.show_menu_panel(interaction)


class VoiceLobbyJoinRolesView(discord.ui.View):
    def __init__(self, adapter: "VoiceLobbyConfigAdapter") -> None:
        super().__init__(timeout=60)
        self._adapter = adapter

    @discord.ui.button(
        label="Add Role", style=discord.ButtonStyle.success, emoji="➕", row=0
    )
    async def add_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Select a role to allow lobby joins:",
            embed=None,
            view=AddVoiceJoinRoleView(self._adapter),
        )

    @discord.ui.button(
        label="Remove Role", style=discord.ButtonStyle.secondary, emoji="➖", row=0
    )
    async def remove_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Select a role to remove from lobby joiners:",
            embed=None,
            view=RemoveVoiceJoinRoleView(self._adapter),
        )

    @discord.ui.button(
        label="Clear Roles", style=discord.ButtonStyle.danger, emoji="🗑️", row=0
    )
    async def clear_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._adapter.clear_join_roles(interaction)

    @discord.ui.button(
        label="Back", style=discord.ButtonStyle.secondary, emoji="↩️", row=1
    )
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._adapter.show_menu_panel(interaction)


class AddVoiceCreateRoleView(discord.ui.View):
    def __init__(self, adapter: "VoiceLobbyConfigAdapter") -> None:
        super().__init__(timeout=60)
        self._adapter = adapter

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Select a role to add...")
    async def role_select(
        self, interaction: discord.Interaction, select: discord.ui.RoleSelect
    ) -> None:
        await self._adapter.add_creator_role(interaction, select.values[0])

    @discord.ui.button(
        label="Back", style=discord.ButtonStyle.secondary, emoji="↩️", row=1
    )
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Configure roles allowed to create lobbies:",
            embed=None,
            view=VoiceLobbyCreateRolesView(self._adapter),
        )


class RemoveVoiceCreateRoleView(discord.ui.View):
    def __init__(self, adapter: "VoiceLobbyConfigAdapter") -> None:
        super().__init__(timeout=60)
        self._adapter = adapter

    @discord.ui.select(
        cls=discord.ui.RoleSelect, placeholder="Select a role to remove..."
    )
    async def role_select(
        self, interaction: discord.Interaction, select: discord.ui.RoleSelect
    ) -> None:
        await self._adapter.remove_creator_role(interaction, select.values[0])

    @discord.ui.button(
        label="Back", style=discord.ButtonStyle.secondary, emoji="↩️", row=1
    )
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Configure roles allowed to create lobbies:",
            embed=None,
            view=VoiceLobbyCreateRolesView(self._adapter),
        )


class AddVoiceJoinRoleView(discord.ui.View):
    def __init__(self, adapter: "VoiceLobbyConfigAdapter") -> None:
        super().__init__(timeout=60)
        self._adapter = adapter

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Select a role to add...")
    async def role_select(
        self, interaction: discord.Interaction, select: discord.ui.RoleSelect
    ) -> None:
        await self._adapter.add_join_role(interaction, select.values[0])

    @discord.ui.button(
        label="Back", style=discord.ButtonStyle.secondary, emoji="↩️", row=1
    )
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Configure roles allowed to join lobbies:",
            embed=None,
            view=VoiceLobbyJoinRolesView(self._adapter),
        )


class RemoveVoiceJoinRoleView(discord.ui.View):
    def __init__(self, adapter: "VoiceLobbyConfigAdapter") -> None:
        super().__init__(timeout=60)
        self._adapter = adapter

    @discord.ui.select(
        cls=discord.ui.RoleSelect, placeholder="Select a role to remove..."
    )
    async def role_select(
        self, interaction: discord.Interaction, select: discord.ui.RoleSelect
    ) -> None:
        await self._adapter.remove_join_role(interaction, select.values[0])

    @discord.ui.button(
        label="Back", style=discord.ButtonStyle.secondary, emoji="↩️", row=1
    )
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Configure roles allowed to join lobbies:",
            embed=None,
            view=VoiceLobbyJoinRolesView(self._adapter),
        )
