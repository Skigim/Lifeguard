"""Cross-cutting configuration UI views and modals.

These views power the /config menu hierarchy and are module-agnostic.
Content-review-specific views remain in
``lifeguard.modules.content_review.views.config_ui``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from lifeguard.cogs.config_cog import ConfigCog

LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Top-level config menu
# ---------------------------------------------------------------------------


class ConfigFeatureSelectView(discord.ui.View):
    """First-level config menu for choosing which feature to configure."""

    def __init__(self, cog: "ConfigCog") -> None:
        super().__init__(timeout=120)
        self.cog = cog
        if not cog.bot.get_cog("AlbionCog"):
            self.remove_item(self.albion_button)

    @discord.ui.button(
        label="General Settings",
        style=discord.ButtonStyle.secondary,
        emoji="⚙️",
        row=0,
    )
    async def general_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_general_menu(interaction)

    @discord.ui.button(
        label="Content Review",
        style=discord.ButtonStyle.primary,
        emoji="📝",
        row=0,
    )
    async def content_review_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_content_review_menu(interaction)

    @discord.ui.button(
        label="Time Impersonator",
        style=discord.ButtonStyle.secondary,
        emoji="🕐",
        row=0,
    )
    async def time_impersonator_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_time_impersonator_menu(interaction)

    @discord.ui.button(
        label="Voice Lobby",
        style=discord.ButtonStyle.secondary,
        emoji="🎧",
        row=1,
    )
    async def voice_lobby_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_voice_lobby_menu(interaction)

    @discord.ui.button(
        label="Albion Features",
        style=discord.ButtonStyle.secondary,
        emoji="⚔️",
        row=1,
    )
    async def albion_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_albion_menu(interaction)


# ---------------------------------------------------------------------------
# General settings
# ---------------------------------------------------------------------------


class GeneralConfigView(discord.ui.View):
    """Config menu for general bot settings."""

    def __init__(self, cog: "ConfigCog") -> None:
        super().__init__(timeout=120)
        self.cog = cog

    @discord.ui.button(label="View Admin Roles", style=discord.ButtonStyle.secondary, emoji="📋", row=0)
    async def view_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_bot_admin_roles(interaction)

    @discord.ui.button(label="Add Admin Role", style=discord.ButtonStyle.success, emoji="➕", row=0)
    async def add_role_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        view = AddBotAdminRoleView(self.cog)
        await interaction.response.edit_message(
            content="Select a role to add as a bot admin role:", embed=None, view=view
        )

    @discord.ui.button(label="Remove Admin Role", style=discord.ButtonStyle.secondary, emoji="➖", row=0)
    async def remove_role_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_remove_bot_admin_role_view(interaction)

    @discord.ui.button(label="Clear Admin Roles", style=discord.ButtonStyle.danger, emoji="🗑️", row=1)
    async def clear_roles_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._clear_bot_admin_roles(interaction)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️", row=1)
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_config_home(interaction)


class AddBotAdminRoleView(discord.ui.View):
    """View for adding a bot admin role."""

    def __init__(self, cog: "ConfigCog") -> None:
        super().__init__(timeout=60)
        self.cog = cog

    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="Select a role to add...",
    )
    async def role_select(
        self, interaction: discord.Interaction, select: discord.ui.RoleSelect
    ) -> None:
        role = select.values[0]
        await self.cog._add_bot_admin_role(interaction, role)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️", row=1)
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_general_menu(interaction)


class RemoveBotAdminRoleView(discord.ui.View):
    """View for removing a bot admin role."""

    def __init__(self, cog: "ConfigCog", role_ids: list[int]) -> None:
        super().__init__(timeout=60)
        self.cog = cog
        self.role_ids = role_ids

    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="Select a role to remove...",
    )
    async def role_select(
        self, interaction: discord.Interaction, select: discord.ui.RoleSelect
    ) -> None:
        role = select.values[0]
        await self.cog._remove_bot_admin_role(interaction, role)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️", row=1)
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_general_menu(interaction)


class BackToGeneralView(discord.ui.View):
    """Simple back navigation view to General Settings."""

    def __init__(self, cog: "ConfigCog") -> None:
        super().__init__(timeout=120)
        self.cog = cog

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️")
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_general_menu(interaction)


# ---------------------------------------------------------------------------
# Albion config
# ---------------------------------------------------------------------------


class AlbionConfigView(discord.ui.View):
    """Config menu for Albion features."""

    def __init__(self, cog: "ConfigCog") -> None:
        super().__init__(timeout=120)
        self.cog = cog

    @discord.ui.button(label="Status", style=discord.ButtonStyle.secondary, emoji="📋", row=0)
    async def view_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_albion_status(interaction)

    @discord.ui.button(label="Enable Prices", style=discord.ButtonStyle.success, emoji="💰", row=0)
    async def enable_prices_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._enable_albion_feature(interaction, "prices")

    @discord.ui.button(label="Disable Prices", style=discord.ButtonStyle.danger, emoji="❌", row=0)
    async def disable_prices_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._disable_albion_feature(interaction, "prices")

    @discord.ui.button(label="Enable Builds", style=discord.ButtonStyle.success, emoji="⚔️", row=0)
    async def enable_builds_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._enable_albion_feature(interaction, "builds")

    @discord.ui.button(label="Disable Builds", style=discord.ButtonStyle.danger, emoji="❌", row=0)
    async def disable_builds_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._disable_albion_feature(interaction, "builds")

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️", row=1)
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_config_home(interaction)


class BackToAlbionView(discord.ui.View):
    """Simple back navigation view to Albion menu."""

    def __init__(self, cog: "ConfigCog") -> None:
        super().__init__(timeout=120)
        self.cog = cog

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️")
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_albion_menu(interaction)


# ---------------------------------------------------------------------------
# Voice Lobby config
# ---------------------------------------------------------------------------


class VoiceLobbyConfigView(discord.ui.View):
    """Config menu for Voice Lobby feature defaults."""

    def __init__(self, cog: "ConfigCog") -> None:
        super().__init__(timeout=120)
        self.cog = cog

    @discord.ui.button(label="Status", style=discord.ButtonStyle.secondary, emoji="📋", row=0)
    async def status_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_voice_lobby_status(interaction)

    @discord.ui.button(label="Entry Channel", style=discord.ButtonStyle.secondary, emoji="🎙️", row=0)
    async def entry_channel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Select the entry voice channel:",
            embed=None,
            view=AssignVoiceEntryChannelView(self.cog),
        )

    @discord.ui.button(label="Lobby Category", style=discord.ButtonStyle.secondary, emoji="🗂️", row=0)
    async def lobby_category_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Select the category for temporary lobbies, or use entry-channel category:",
            embed=None,
            view=AssignVoiceLobbyCategoryView(self.cog),
        )

    @discord.ui.button(label="Defaults", style=discord.ButtonStyle.primary, emoji="⚙️", row=0)
    async def defaults_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(VoiceLobbyDefaultsModal(self.cog))

    @discord.ui.button(label="Create Roles", style=discord.ButtonStyle.secondary, emoji="➕", row=1)
    async def create_roles_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Configure roles allowed to create lobbies:",
            embed=None,
            view=VoiceLobbyCreateRolesView(self.cog),
        )

    @discord.ui.button(label="Join Roles", style=discord.ButtonStyle.secondary, emoji="👥", row=1)
    async def join_roles_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Configure roles allowed to join lobbies:",
            embed=None,
            view=VoiceLobbyJoinRolesView(self.cog),
        )

    @discord.ui.button(label="Disable", style=discord.ButtonStyle.danger, emoji="❌", row=1)
    async def disable_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._disable_voice_lobby(interaction)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️", row=1)
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_config_home(interaction)


class AssignVoiceEntryChannelView(discord.ui.View):
    """Select entry voice channel for temporary lobbies."""

    def __init__(self, cog: "ConfigCog") -> None:
        super().__init__(timeout=60)
        self.cog = cog

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
            await interaction.response.send_message("This must be used in a guild.", ephemeral=True)
            return

        selected_channel = select.values[0]
        channel = interaction.guild.get_channel(selected_channel.id)
        if not isinstance(channel, discord.VoiceChannel):
            await interaction.response.send_message("Please select a voice channel.", ephemeral=True)
            return

        await self.cog._set_voice_lobby_entry_channel(interaction, channel)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️", row=1)
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_voice_lobby_menu(interaction)


class AssignVoiceLobbyCategoryView(discord.ui.View):
    """Select category for temporary lobby channels."""

    def __init__(self, cog: "ConfigCog") -> None:
        super().__init__(timeout=60)
        self.cog = cog

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
            await interaction.response.send_message("This must be used in a guild.", ephemeral=True)
            return

        selected_channel = select.values[0]
        category = interaction.guild.get_channel(selected_channel.id)
        if not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message("Please select a valid category.", ephemeral=True)
            return

        await self.cog._set_voice_lobby_category(interaction, category)

    @discord.ui.button(label="Use Entry Category", style=discord.ButtonStyle.secondary, emoji="📍", row=1)
    async def use_entry_category_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._set_voice_lobby_category(interaction, None)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️", row=1)
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_voice_lobby_menu(interaction)


class VoiceLobbyDefaultsModal(discord.ui.Modal, title="Voice Lobby Defaults"):
    """Set default name template and user limit."""

    name_template = discord.ui.TextInput(
        label="Name Template",
        placeholder="Lobby - {owner}",
        required=False,
        max_length=100,
    )
    default_user_limit = discord.ui.TextInput(
        label="Default User Limit (0-99)",
        placeholder="0",
        default="0",
        max_length=2,
    )

    def __init__(self, cog: "ConfigCog") -> None:
        super().__init__()
        self.cog = cog

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

        await self.cog._set_voice_lobby_defaults(interaction, template, user_limit)


class VoiceLobbyCreateRolesView(discord.ui.View):
    """Manage roles that can create lobbies."""

    def __init__(self, cog: "ConfigCog") -> None:
        super().__init__(timeout=60)
        self.cog = cog

    @discord.ui.button(label="Add Role", style=discord.ButtonStyle.success, emoji="➕", row=0)
    async def add_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Select a role to allow lobby creation:",
            embed=None,
            view=AddVoiceCreateRoleView(self.cog),
        )

    @discord.ui.button(label="Remove Role", style=discord.ButtonStyle.secondary, emoji="➖", row=0)
    async def remove_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Select a role to remove from lobby creators:",
            embed=None,
            view=RemoveVoiceCreateRoleView(self.cog),
        )

    @discord.ui.button(label="Clear Roles", style=discord.ButtonStyle.danger, emoji="🗑️", row=0)
    async def clear_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._clear_voice_lobby_creator_roles(interaction)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️", row=1)
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_voice_lobby_menu(interaction)


class VoiceLobbyJoinRolesView(discord.ui.View):
    """Manage roles that can join temporary lobbies."""

    def __init__(self, cog: "ConfigCog") -> None:
        super().__init__(timeout=60)
        self.cog = cog

    @discord.ui.button(label="Add Role", style=discord.ButtonStyle.success, emoji="➕", row=0)
    async def add_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Select a role to allow lobby joins:",
            embed=None,
            view=AddVoiceJoinRoleView(self.cog),
        )

    @discord.ui.button(label="Remove Role", style=discord.ButtonStyle.secondary, emoji="➖", row=0)
    async def remove_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Select a role to remove from lobby joiners:",
            embed=None,
            view=RemoveVoiceJoinRoleView(self.cog),
        )

    @discord.ui.button(label="Clear Roles", style=discord.ButtonStyle.danger, emoji="🗑️", row=0)
    async def clear_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._clear_voice_lobby_join_roles(interaction)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️", row=1)
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_voice_lobby_menu(interaction)


class AddVoiceCreateRoleView(discord.ui.View):
    def __init__(self, cog: "ConfigCog") -> None:
        super().__init__(timeout=60)
        self.cog = cog

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Select a role to add...")
    async def role_select(
        self, interaction: discord.Interaction, select: discord.ui.RoleSelect
    ) -> None:
        await self.cog._add_voice_lobby_creator_role(interaction, select.values[0])

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️", row=1)
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Configure roles allowed to create lobbies:",
            embed=None,
            view=VoiceLobbyCreateRolesView(self.cog),
        )


class RemoveVoiceCreateRoleView(discord.ui.View):
    def __init__(self, cog: "ConfigCog") -> None:
        super().__init__(timeout=60)
        self.cog = cog

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Select a role to remove...")
    async def role_select(
        self, interaction: discord.Interaction, select: discord.ui.RoleSelect
    ) -> None:
        await self.cog._remove_voice_lobby_creator_role(interaction, select.values[0])

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️", row=1)
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Configure roles allowed to create lobbies:",
            embed=None,
            view=VoiceLobbyCreateRolesView(self.cog),
        )


class AddVoiceJoinRoleView(discord.ui.View):
    def __init__(self, cog: "ConfigCog") -> None:
        super().__init__(timeout=60)
        self.cog = cog

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Select a role to add...")
    async def role_select(
        self, interaction: discord.Interaction, select: discord.ui.RoleSelect
    ) -> None:
        await self.cog._add_voice_lobby_join_role(interaction, select.values[0])

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️", row=1)
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Configure roles allowed to join lobbies:",
            embed=None,
            view=VoiceLobbyJoinRolesView(self.cog),
        )


class RemoveVoiceJoinRoleView(discord.ui.View):
    def __init__(self, cog: "ConfigCog") -> None:
        super().__init__(timeout=60)
        self.cog = cog

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Select a role to remove...")
    async def role_select(
        self, interaction: discord.Interaction, select: discord.ui.RoleSelect
    ) -> None:
        await self.cog._remove_voice_lobby_join_role(interaction, select.values[0])

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️", row=1)
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Configure roles allowed to join lobbies:",
            embed=None,
            view=VoiceLobbyJoinRolesView(self.cog),
        )


# ---------------------------------------------------------------------------
# Time Impersonator config
# ---------------------------------------------------------------------------


class TimeImpersonatorConfigView(discord.ui.View):
    """Config sub-menu for Time Impersonator feature."""

    def __init__(self, cog: "ConfigCog") -> None:
        super().__init__(timeout=120)
        self.cog = cog

    @discord.ui.button(label="Status", style=discord.ButtonStyle.secondary, emoji="📋", row=0)
    async def status_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_time_impersonator_status(interaction)

    @discord.ui.button(label="Enable", style=discord.ButtonStyle.success, emoji="✅", row=0)
    async def enable_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._enable_time_impersonator(interaction)

    @discord.ui.button(label="Disable", style=discord.ButtonStyle.danger, emoji="❌", row=0)
    async def disable_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._disable_time_impersonator(interaction)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️", row=1)
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_config_home(interaction)


# ---------------------------------------------------------------------------
# Content Review disabled placeholder
# ---------------------------------------------------------------------------


class ContentReviewDisabledView(discord.ui.View):
    """Shown when Content Review is not enabled; offers Enable or Back."""

    def __init__(self, cog: "ConfigCog") -> None:
        super().__init__(timeout=120)
        self.cog = cog

    @discord.ui.button(label="Enable Content Review", style=discord.ButtonStyle.success, emoji="✅")
    async def enable_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        cr_cog = self.cog.bot.get_cog("ContentReviewCog")
        if not cr_cog:
            await interaction.response.send_message(
                "Content Review module is not loaded.", ephemeral=True
            )
            return
        try:
            from lifeguard.modules.content_review.views.config_ui import ContentReviewSetupView
        except ImportError:
            LOGGER.exception("Failed to import ContentReviewSetupView")
            await interaction.response.send_message(
                "Content Review module failed to load.", ephemeral=True
            )
            return

        view = ContentReviewSetupView(cr_cog)
        embed = discord.Embed(
            title="📝 Content Review Setup",
            description=(
                "Select the **ticket category** where review channels will be created.\n\n"
                "The submit button will be posted in the current channel."
            ),
            color=discord.Color.blue(),
        )
        await interaction.response.edit_message(content=None, embed=embed, view=view)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️")
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_config_home(interaction)
