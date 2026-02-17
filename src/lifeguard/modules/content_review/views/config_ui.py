"""Config UI views and modals for the Content Review module."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from lifeguard.modules.content_review import repo
from lifeguard.modules.content_review.config import (
    ContentReviewConfig,
    ReviewCategory,
    SubmissionField,
)

if TYPE_CHECKING:
    from lifeguard.modules.content_review.cog import ContentReviewCog


class ContentReviewSetupView(discord.ui.View):
    """View for setting up content review."""

    def __init__(self, cog: "ContentReviewCog") -> None:
        super().__init__(timeout=120)
        self.cog = cog

    @discord.ui.button(label="Configure & Enable", style=discord.ButtonStyle.success)
    async def configure_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(EnableContentReviewModal(self.cog))

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Setup cancelled.", embed=None, view=None
        )


class ConfigFeatureSelectView(discord.ui.View):
    """First-level config menu for choosing which feature to configure."""

    def __init__(self, cog: "ContentReviewCog") -> None:
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


class GeneralConfigView(discord.ui.View):
    """Config menu for general bot settings."""

    def __init__(self, cog: "ContentReviewCog") -> None:
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

    def __init__(self, cog: "ContentReviewCog") -> None:
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

    def __init__(self, cog: "ContentReviewCog", role_ids: list[int]) -> None:
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


class ContentReviewConfigView(discord.ui.View):
    """Config menu for Content Review feature."""

    def __init__(self, cog: "ContentReviewCog") -> None:
        super().__init__(timeout=120)
        self.cog = cog

    @discord.ui.button(label="View Config", style=discord.ButtonStyle.secondary, emoji="📋", row=0)
    async def view_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_config(interaction)

    @discord.ui.button(label="Sticky Message", style=discord.ButtonStyle.secondary, emoji="📌", row=0)
    async def sticky_menu_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_sticky_menu(interaction)

    @discord.ui.button(label="Review Roles", style=discord.ButtonStyle.secondary, emoji="👥", row=0)
    async def review_roles_menu_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_reviewer_roles_menu(interaction)

    @discord.ui.button(label="Edit Form", style=discord.ButtonStyle.secondary, emoji="🧩", row=0)
    async def edit_form_menu_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_form_editor_menu(interaction)

    @discord.ui.button(label="Settings", style=discord.ButtonStyle.secondary, emoji="⚙️", row=0)
    async def settings_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Configure settings:", embed=None, view=SettingsView(self.cog)
        )

    @discord.ui.button(label="Disable", style=discord.ButtonStyle.danger, emoji="❌", row=1)
    async def disable_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._disable_content_review(interaction)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️", row=1)
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_config_home(interaction)


class StickyConfigMenuView(discord.ui.View):
    """Nested config menu for sticky message actions."""

    def __init__(self, cog: "ContentReviewCog") -> None:
        super().__init__(timeout=120)
        self.cog = cog

    @discord.ui.button(label="Edit Sticky", style=discord.ButtonStyle.secondary, emoji="✏️", row=0)
    async def edit_sticky_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message(
                "This command must be used in a guild.",
                ephemeral=True,
            )
            return
        config = repo.get_or_create_config(self.cog.firestore, interaction.guild.id)
        await interaction.response.send_modal(SetStickyModal(self.cog, config))

    @discord.ui.button(label="Repost Submit", style=discord.ButtonStyle.secondary, emoji="🔄", row=0)
    async def repost_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._repost_button(interaction)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️", row=1)
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_content_review_menu(interaction)


class ReviewerRolesMenuView(discord.ui.View):
    """Nested config menu for reviewer role management."""

    def __init__(self, cog: "ContentReviewCog") -> None:
        super().__init__(timeout=120)
        self.cog = cog

    @discord.ui.button(label="Add Role", style=discord.ButtonStyle.success, emoji="➕", row=0)
    async def add_role_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        view = AddRoleView(self.cog)
        await interaction.response.edit_message(
            content="Select a role to add as a reviewer:",
            embed=None,
            view=view,
        )

    @discord.ui.button(label="Remove Role", style=discord.ButtonStyle.secondary, emoji="➖", row=0)
    async def remove_role_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_remove_role_view(interaction)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️", row=1)
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_content_review_menu(interaction)


class EditFormMenuView(discord.ui.View):
    """Nested config menu for form/category/category-channel editing."""

    def __init__(self, cog: "ContentReviewCog") -> None:
        super().__init__(timeout=120)
        self.cog = cog

    @discord.ui.button(label="Add Field", style=discord.ButtonStyle.primary, emoji="📝", row=0)
    async def add_field_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(AddFieldModal(self.cog))

    @discord.ui.button(label="Remove Field", style=discord.ButtonStyle.secondary, emoji="🗑️", row=0)
    async def remove_field_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_remove_field_view(interaction)

    @discord.ui.button(label="Add Category", style=discord.ButtonStyle.primary, emoji="⭐", row=0)
    async def add_category_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(AddCategoryModal(self.cog))

    @discord.ui.button(label="Remove Category", style=discord.ButtonStyle.secondary, emoji="🗑️", row=0)
    async def remove_category_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_remove_category_view(interaction)

    @discord.ui.button(label="Ticket Category", style=discord.ButtonStyle.secondary, emoji="🗂️", row=1)
    async def ticket_category_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Select the category where review tickets should be created:",
            embed=None,
            view=AssignTicketCategoryView(self.cog),
        )

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️", row=1)
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_content_review_menu(interaction)


class AlbionConfigView(discord.ui.View):
    """Config menu for Albion features."""

    def __init__(self, cog: "ContentReviewCog") -> None:
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


class VoiceLobbyConfigView(discord.ui.View):
    """Config menu for Voice Lobby feature defaults."""

    def __init__(self, cog: "ContentReviewCog") -> None:
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

    def __init__(self, cog: "ContentReviewCog") -> None:
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

    def __init__(self, cog: "ContentReviewCog") -> None:
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

    def __init__(self, cog: "ContentReviewCog") -> None:
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

    def __init__(self, cog: "ContentReviewCog") -> None:
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

    def __init__(self, cog: "ContentReviewCog") -> None:
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
    def __init__(self, cog: "ContentReviewCog") -> None:
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
    def __init__(self, cog: "ContentReviewCog") -> None:
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
    def __init__(self, cog: "ContentReviewCog") -> None:
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
    def __init__(self, cog: "ContentReviewCog") -> None:
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


class AddRoleView(discord.ui.View):
    """View for adding a reviewer role."""

    def __init__(self, cog: "ContentReviewCog") -> None:
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
        await self.cog._add_reviewer_role(interaction, role)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️", row=1)
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_reviewer_roles_menu(interaction)


class AssignTicketCategoryView(discord.ui.View):
    """View for assigning the ticket category."""

    def __init__(self, cog: "ContentReviewCog") -> None:
        super().__init__(timeout=60)
        self.cog = cog

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        placeholder="Select a ticket category...",
        channel_types=[discord.ChannelType.category],
        min_values=1,
        max_values=1,
    )
    async def category_select(
        self, interaction: discord.Interaction, select: discord.ui.ChannelSelect
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message(
                "This command must be used in a guild.",
                ephemeral=True,
            )
            return

        selected_channel = select.values[0]
        category = interaction.guild.get_channel(selected_channel.id)
        if not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message(
                "Please select a valid category.",
                ephemeral=True,
            )
            return
        await self.cog._set_ticket_category(interaction, category)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️", row=1)
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_form_editor_menu(interaction)


class RemoveRoleView(discord.ui.View):
    """View for removing a reviewer role."""

    def __init__(self, cog: "ContentReviewCog", role_ids: list[int]) -> None:
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
        await self.cog._remove_reviewer_role(interaction, role)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️", row=1)
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_reviewer_roles_menu(interaction)


class EnableContentReviewModal(discord.ui.Modal, title="Enable Content Review"):
    """Modal for enabling content review without dropdowns."""

    ticket_category = discord.ui.TextInput(
        label="Ticket Category",
        placeholder="Category ID or mention (e.g. 123... or <#123...>)",
        max_length=40,
    )
    reviewer_role = discord.ui.TextInput(
        label="Reviewer Role (optional)",
        placeholder="Role ID or mention (e.g. 123... or <@&123...>)",
        required=False,
        max_length=40,
    )

    def __init__(self, cog: "ContentReviewCog") -> None:
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return

        category = self.cog._resolve_category_from_input(
            interaction.guild, self.ticket_category.value.strip()
        )
        if category is None:
            await interaction.response.send_message(
                "Could not find that category. Use a valid category ID or mention.",
                ephemeral=True,
            )
            return

        reviewer_role_value = self.reviewer_role.value.strip()
        role: discord.Role | None = None
        if reviewer_role_value:
            role = self.cog._resolve_role_from_input(interaction.guild, reviewer_role_value)
            if role is None:
                await interaction.response.send_message(
                    "Could not find that role. Use a valid role ID or mention.",
                    ephemeral=True,
                )
                return

        await self.cog._enable_content_review(interaction, category, role, use_send=True)


class RemoveFieldByIdModal(discord.ui.Modal, title="Remove Submission Field"):
    """Modal for removing a submission field by ID."""

    field_id = discord.ui.TextInput(
        label="Field ID",
        placeholder="e.g. game_link",
        max_length=50,
    )

    def __init__(self, cog: "ContentReviewCog") -> None:
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog._remove_field(interaction, self.field_id.value.strip(), use_send=True)


class RemoveCategoryByIdModal(discord.ui.Modal, title="Remove Review Category"):
    """Modal for removing a review category by ID."""

    category_id = discord.ui.TextInput(
        label="Category ID",
        placeholder="e.g. gameplay",
        max_length=50,
    )

    def __init__(self, cog: "ContentReviewCog") -> None:
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog._remove_category(
            interaction, self.category_id.value.strip(), use_send=True
        )


class AddFieldModal(discord.ui.Modal, title="Add Submission Field"):
    """Modal for adding a submission field."""

    field_id = discord.ui.TextInput(
        label="Field ID",
        placeholder="e.g., game_link",
        max_length=50,
    )
    label = discord.ui.TextInput(
        label="Display Label",
        placeholder="e.g., Game Link",
        max_length=45,
    )
    field_type = discord.ui.TextInput(
        label="Field Type",
        placeholder="short_text, paragraph, or url",
        default="short_text",
        max_length=20,
    )
    placeholder = discord.ui.TextInput(
        label="Placeholder Text",
        placeholder="Hint text shown in the input",
        required=False,
        max_length=100,
    )
    required = discord.ui.TextInput(
        label="Required? (yes/no)",
        placeholder="yes",
        default="yes",
        max_length=3,
    )

    def __init__(self, cog: "ContentReviewCog") -> None:
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        field_type = self.field_type.value.lower().strip()
        if field_type not in ("short_text", "paragraph", "url"):
            field_type = "short_text"

        is_required = self.required.value.lower().strip() in ("yes", "y", "true", "1")

        await self.cog._add_field(
            interaction,
            field_id=self.field_id.value.strip(),
            label=self.label.value.strip(),
            field_type=field_type,
            placeholder=self.placeholder.value.strip(),
            required=is_required,
        )


class RemoveFieldView(discord.ui.View):
    """View for removing a submission field."""

    def __init__(self, cog: "ContentReviewCog", fields: list[SubmissionField]) -> None:
        super().__init__(timeout=60)
        self.cog = cog
        self.fields = fields

    @discord.ui.button(label="Enter Field ID", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def open_modal(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(RemoveFieldByIdModal(self.cog))

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️", row=1)
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_form_editor_menu(interaction)


class AddCategoryModal(discord.ui.Modal, title="Add Review Category"):
    """Modal for adding a review category."""

    category_id = discord.ui.TextInput(
        label="Category ID",
        placeholder="e.g., gameplay",
        max_length=50,
    )
    name = discord.ui.TextInput(
        label="Display Name",
        placeholder="e.g., Gameplay",
        max_length=50,
    )
    description = discord.ui.TextInput(
        label="Description (help text for reviewers)",
        placeholder="How well did the player perform?",
        required=False,
        max_length=200,
    )
    score_range = discord.ui.TextInput(
        label="Score Range (min-max)",
        placeholder="1-5",
        default="1-5",
        max_length=10,
    )

    def __init__(self, cog: "ContentReviewCog") -> None:
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            parts = self.score_range.value.split("-")
            min_score = int(parts[0].strip())
            max_score = int(parts[1].strip()) if len(parts) > 1 else 5
        except (ValueError, IndexError):
            min_score, max_score = 1, 5

        if min_score > max_score:
            min_score, max_score = max_score, min_score

        await self.cog._add_category(
            interaction,
            category_id=self.category_id.value.strip(),
            name=self.name.value.strip(),
            description=self.description.value.strip(),
            min_score=min_score,
            max_score=max_score,
        )


class RemoveCategoryView(discord.ui.View):
    """View for removing a review category."""

    def __init__(self, cog: "ContentReviewCog", categories: list[ReviewCategory]) -> None:
        super().__init__(timeout=60)
        self.cog = cog
        self.categories = categories

    @discord.ui.button(label="Enter Category ID", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def open_modal(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(RemoveCategoryByIdModal(self.cog))

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️", row=1)
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_form_editor_menu(interaction)


class SetStickyModal(discord.ui.Modal, title="Customize Sticky Message"):
    """Modal for customizing the sticky submit message."""

    sticky_title = discord.ui.TextInput(
        label="Title",
        placeholder="📥 Content Review",
        required=False,
        max_length=100,
    )
    sticky_description = discord.ui.TextInput(
        label="Description",
        placeholder="Submit your content for feedback!",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500,
    )
    button_label = discord.ui.TextInput(
        label="Button Label",
        placeholder="Submit Content",
        required=False,
        max_length=50,
    )
    button_emoji = discord.ui.TextInput(
        label="Button Emoji",
        placeholder="📝",
        required=False,
        max_length=10,
    )

    def __init__(self, cog: "ContentReviewCog", config: ContentReviewConfig) -> None:
        super().__init__()
        self.cog = cog
        self.sticky_title.default = config.sticky_title
        self.sticky_description.default = config.sticky_description
        self.button_label.default = config.sticky_button_label
        self.button_emoji.default = config.sticky_button_emoji

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog._set_sticky(
            interaction,
            title=self.sticky_title.value.strip() or None,
            description=self.sticky_description.value.strip() or None,
            button_label=self.button_label.value.strip() or None,
            button_emoji=self.button_emoji.value.strip() or None,
        )


class SettingsView(discord.ui.View):
    """View for configuring misc settings."""

    def __init__(self, cog: "ContentReviewCog") -> None:
        super().__init__(timeout=60)
        self.cog = cog

    @discord.ui.button(
        label="Toggle DM on Complete",
        style=discord.ButtonStyle.secondary,
        emoji="📬",
        row=0,
    )
    async def toggle_dm_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._toggle_dm(interaction)

    @discord.ui.button(
        label="Toggle Leaderboard",
        style=discord.ButtonStyle.secondary,
        emoji="🏆",
        row=0,
    )
    async def toggle_leaderboard_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._toggle_leaderboard(interaction)

    @discord.ui.button(
        label="Set Review Timeout",
        style=discord.ButtonStyle.primary,
        emoji="⏱️",
        row=0,
    )
    async def set_timeout_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        modal = TimeoutModal(self.cog)
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Back",
        style=discord.ButtonStyle.secondary,
        emoji="↩️",
        row=1,
    )
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_content_review_menu(interaction)


class TimeoutModal(discord.ui.Modal, title="Set Review Timeout"):
    """Modal for setting review timeout."""

    timeout_minutes = discord.ui.TextInput(
        label="Timeout (minutes)",
        placeholder="15",
        default="15",
        max_length=5,
    )

    def __init__(self, cog: "ContentReviewCog") -> None:
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            minutes = int(self.timeout_minutes.value.strip())
        except ValueError:
            minutes = 15
        if minutes < 1 or minutes > 1440:
            minutes = 15
        await self.cog._set_timeout(interaction, minutes)


class BackToGeneralView(discord.ui.View):
    """Simple back navigation view to General Settings."""

    def __init__(self, cog: "ContentReviewCog") -> None:
        super().__init__(timeout=120)
        self.cog = cog

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️")
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_general_menu(interaction)


class BackToContentReviewView(discord.ui.View):
    """Simple back navigation view to Content Review menu."""

    def __init__(self, cog: "ContentReviewCog") -> None:
        super().__init__(timeout=120)
        self.cog = cog

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️")
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_content_review_menu(interaction)


class BackToAlbionView(discord.ui.View):
    """Simple back navigation view to Albion menu."""

    def __init__(self, cog: "ContentReviewCog") -> None:
        super().__init__(timeout=120)
        self.cog = cog

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️")
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_albion_menu(interaction)


class ContentReviewDisabledView(discord.ui.View):
    """Shown when Content Review is not enabled; offers Enable or Back."""

    def __init__(self, cog: "ContentReviewCog") -> None:
        super().__init__(timeout=120)
        self.cog = cog

    @discord.ui.button(label="Enable Content Review", style=discord.ButtonStyle.success, emoji="✅")
    async def enable_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        view = ContentReviewSetupView(self.cog)
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


class TimeImpersonatorConfigView(discord.ui.View):
    """Config sub-menu for Time Impersonator feature."""

    def __init__(self, cog: "ContentReviewCog") -> None:
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
