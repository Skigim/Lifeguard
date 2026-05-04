"""Cross-cutting configuration UI views.

This module only contains the generic shell and general-settings views.
Feature-specific config UI lives under each feature module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from lifeguard.cogs.config_cog import ConfigCog
    from lifeguard.features.availability import FeatureEntry


class ConfigFeatureSelect(discord.ui.Select):
    def __init__(self, cog: "ConfigCog", feature_entries: list["FeatureEntry"]) -> None:
        options = [
            discord.SelectOption(
                label=entry.display_name,
                value=entry.feature_key,
                description=entry.description[:100],
                emoji=entry.emoji,
            )
            for entry in feature_entries
        ]
        super().__init__(placeholder="Choose a feature...", options=options)
        self.cog = cog

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.cog._dispatch_feature_menu(interaction, self.values[0])


class ConfigHomeView(discord.ui.View):
    def __init__(self, cog: "ConfigCog", feature_entries: list["FeatureEntry"]) -> None:
        super().__init__(timeout=120)
        self.cog = cog
        if feature_entries:
            self.add_item(ConfigFeatureSelect(cog, feature_entries))

    @discord.ui.button(
        label="General Settings",
        style=discord.ButtonStyle.secondary,
        emoji="⚙️",
        row=1,
    )
    async def general_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_general_menu(interaction)


class ConfigUnavailableFeatureView(discord.ui.View):
    def __init__(self, cog: "ConfigCog") -> None:
        super().__init__(timeout=120)
        self.cog = cog

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️")
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_config_home(interaction)


class GeneralConfigView(discord.ui.View):
    """Config menu for general bot settings."""

    def __init__(self, cog: "ConfigCog") -> None:
        super().__init__(timeout=120)
        self.cog = cog

    @discord.ui.button(
        label="View Admin Roles", style=discord.ButtonStyle.secondary, emoji="📋", row=0
    )
    async def view_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_bot_admin_roles(interaction)

    @discord.ui.button(
        label="Add Admin Role", style=discord.ButtonStyle.success, emoji="➕", row=0
    )
    async def add_role_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        view = AddBotAdminRoleView(self.cog)
        await interaction.response.edit_message(
            content="Select a role to add as a bot admin role:", embed=None, view=view
        )

    @discord.ui.button(
        label="Remove Admin Role",
        style=discord.ButtonStyle.secondary,
        emoji="➖",
        row=0,
    )
    async def remove_role_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_remove_bot_admin_role_view(interaction)

    @discord.ui.button(
        label="Clear Admin Roles", style=discord.ButtonStyle.danger, emoji="🗑️", row=1
    )
    async def clear_roles_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._clear_bot_admin_roles(interaction)

    @discord.ui.button(
        label="Back", style=discord.ButtonStyle.secondary, emoji="↩️", row=1
    )
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

    @discord.ui.button(
        label="Back", style=discord.ButtonStyle.secondary, emoji="↩️", row=1
    )
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

    @discord.ui.button(
        label="Back", style=discord.ButtonStyle.secondary, emoji="↩️", row=1
    )
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
