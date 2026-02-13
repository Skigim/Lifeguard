"""Content Review Cog - Slash commands and event handling."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from lifeguard.modules.content_review import repo
from lifeguard.modules.content_review.config import (
    ContentReviewConfig,
    ReviewCategory,
    SubmissionField,
)
from lifeguard.modules.content_review.embeds import (
    build_leaderboard_embed,
    build_profile_embed,
    build_review_embed,
    build_submission_embed,
)
from lifeguard.modules.content_review.models import ReviewSession, Submission
from lifeguard.modules.content_review.views.review_wizard import (
    DraftReview,
    ReviewWizardView,
)
from lifeguard.modules.content_review.views.submission_modal import SubmissionModal
from lifeguard.modules.albion import repo as albion_repo
from lifeguard.exceptions import FeatureDisabledError

if TYPE_CHECKING:
    from google.cloud.firestore import Client as FirestoreClient

LOGGER = logging.getLogger(__name__)

# --- Common Response Strings ---
_MSG_SERVER_ONLY = "Server only."
_MSG_NO_PERMISSION = "You don't have permission to manage bot settings."
_MSG_GUILD_ONLY = "This command can only be used in a server."
_MSG_NOT_CONFIGURED = "Not configured."
_STATUS_ENABLED = "✅ Enabled"
_STATUS_DISABLED = "❌ Disabled"
_FEATURE_ALBION_PRICES = "Albion Price Lookup"
_FEATURE_ALBION_BUILDS = "Albion Builds"
_FEATURE_CONTENT_REVIEW = "Content Review"


# --- Feature Registry ---
# Central list of all features for autocomplete and validation
# Format: (value, display_name, description, requires_setup)

FEATURES: list[tuple[str, str, str, bool]] = [
    ("content_review", "Content Review", "Review system with tickets, scoring, and leaderboards", True),
    ("time_impersonator", "Time Impersonator", "Send messages with dynamic Discord timestamps", False),
    ("albion_prices", "Albion Prices", "Look up Albion Online market prices", False),
    ("albion_builds", "Albion Builds", "Share and browse Albion Online builds", False),
]


def _get_feature_choices() -> list[app_commands.Choice[str]]:
    """Get all features as Choice objects for autocomplete."""
    return [
        app_commands.Choice(name=f"{display} - {desc}", value=value)
        for value, display, desc, _ in FEATURES
    ]


async def feature_autocomplete(  # NOSONAR - discord.py requires async
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    """Autocomplete handler for feature parameter."""
    current_lower = current.lower()
    choices = []
    for value, display, desc, _ in FEATURES:
        if current_lower in value.lower() or current_lower in display.lower():
            choices.append(app_commands.Choice(name=f"{display} - {desc}", value=value))
    return choices[:25]


def _is_valid_feature(value: str) -> bool:
    """Check if a feature value is valid."""
    return any(f[0] == value for f in FEATURES)


def _feature_requires_setup(value: str) -> bool:
    """Check if a feature requires interactive setup."""
    for f in FEATURES:
        if f[0] == value:
            return f[3]
    return False


# --- Feature Check Decorators ---


def require_content_review():
    """Check that content review is enabled for this guild."""
    async def predicate(interaction: discord.Interaction) -> bool:  # NOSONAR - discord.py requires async
        if not interaction.guild:
            return False
        cog = interaction.client.get_cog("ContentReviewCog")
        if not cog:
            return False
        config = repo.get_config(cog.firestore, interaction.guild.id)
        if not config or not config.enabled:
            raise FeatureDisabledError(_FEATURE_CONTENT_REVIEW)
        return True
    return app_commands.check(predicate)


class StartReviewButton(discord.ui.View):
    """Persistent view with Start Review button."""

    def __init__(self, submission_id: str) -> None:
        super().__init__(timeout=None)
        self.submission_id = submission_id

    @discord.ui.button(
        label="Start Review",
        style=discord.ButtonStyle.success,
        custom_id="content_review:start_review",
    )
    async def start_review(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        # This is handled by the cog's persistent view handler
        pass


class CloseTicketButton(discord.ui.View):
    """Persistent view with Close Ticket button."""

    def __init__(self, submission_id: str) -> None:
        super().__init__(timeout=None)
        self.submission_id = submission_id
        # Set the custom_id with submission_id for the button
        self.close_ticket_btn.custom_id = f"content_review:close_ticket:{submission_id}"

    @discord.ui.button(
        label="Close Ticket",
        style=discord.ButtonStyle.danger,
        custom_id="content_review:close_ticket",
        emoji="🔒",
    )
    async def close_ticket_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        # This is handled by the cog's persistent view handler
        pass


class SubmitButtonView(discord.ui.View):
    """Persistent view with Submit Content button for sticky message."""

    def __init__(self, label: str = "Submit Content", emoji: str = "📝") -> None:
        super().__init__(timeout=None)
        # Create button dynamically with custom label/emoji
        button = discord.ui.Button(
            label=label,
            style=discord.ButtonStyle.primary,
            custom_id="content_review:submit_content",
            emoji=emoji or None,
        )
        button.callback = self._button_callback
        self.add_item(button)

    async def _button_callback(self, interaction: discord.Interaction) -> None:
        # This is handled by the cog's persistent view handler
        pass


# --- Interactive Config Views ---


class ContentReviewSetupView(discord.ui.View):
    """View for setting up content review - category and role selection."""

    def __init__(self, cog: "ContentReviewCog") -> None:
        super().__init__(timeout=120)
        self.cog = cog
        self.selected_category: discord.CategoryChannel | None = None
        self.selected_role: discord.Role | None = None

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        placeholder="Select ticket category...",
        channel_types=[discord.ChannelType.category],
    )
    async def category_select(
        self, interaction: discord.Interaction, select: discord.ui.ChannelSelect
    ) -> None:
        self.selected_category = select.values[0]  # type: ignore
        await interaction.response.defer()

    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="Select reviewer role (optional)...",
        min_values=0,
        max_values=1,
    )
    async def role_select(
        self, interaction: discord.Interaction, select: discord.ui.RoleSelect
    ) -> None:
        self.selected_role = select.values[0] if select.values else None
        await interaction.response.defer()

    @discord.ui.button(label="Enable Content Review", style=discord.ButtonStyle.success)
    async def confirm_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not self.selected_category:
            await interaction.response.send_message(
                "Please select a ticket category first.", ephemeral=True
            )
            return

        await self.cog._enable_content_review(
            interaction, self.selected_category, self.selected_role
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            content="Setup cancelled.", embed=None, view=None
        )


class ConfigFeatureSelect(discord.ui.Select):
    """Dynamic select for choosing which feature to configure."""

    def __init__(self, cog: "ContentReviewCog") -> None:
        self.cog = cog
        options = [
            discord.SelectOption(
                label="General Settings",
                value="general",
                description="Bot user roles and general settings",
                emoji="⚙️",
            ),
            discord.SelectOption(
                label=_FEATURE_CONTENT_REVIEW,
                value="content_review",
                description="Configure the content review system",
                emoji="📝",
            ),
        ]
        # Only show Albion options if the cog is loaded
        if cog.bot.get_cog("AlbionCog"):
            options.append(
                discord.SelectOption(
                    label="Albion Features",
                    value="albion",
                    description="Configure Albion price lookup and builds",
                    emoji="⚔️",
                )
            )
        super().__init__(placeholder="Select a feature to configure...", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.values[0] == "general":
            embed = discord.Embed(
                title="⚙️ General Settings",
                description="Configure general bot settings.",
                color=discord.Color.blue(),
            )
            view = GeneralConfigView(self.cog)
            await interaction.response.edit_message(embed=embed, view=view)
        elif self.values[0] == "content_review":
            config = repo.get_config(self.cog.firestore, interaction.guild.id)
            if not config or not config.enabled:
                await interaction.response.edit_message(
                    content="Content Review is not enabled. Use `/enable-feature` first.",
                    embed=None,
                    view=None,
                )
                return
            embed = discord.Embed(
                title="📝 Content Review Config",
                description="Select a configuration action from the dropdown below.",
                color=discord.Color.blue(),
            )
            view = ContentReviewConfigView(self.cog)
            await interaction.response.edit_message(embed=embed, view=view)
        elif self.values[0] == "albion":
            embed = discord.Embed(
                title="⚔️ Albion Config",
                description="Select a configuration action from the dropdown below.",
                color=discord.Color.blue(),
            )
            view = AlbionConfigView(self.cog)
            await interaction.response.edit_message(embed=embed, view=view)


class ConfigFeatureSelectView(discord.ui.View):
    """First level config menu - select which feature to configure."""

    def __init__(self, cog: "ContentReviewCog") -> None:
        super().__init__(timeout=120)
        self.cog = cog
        self.add_item(ConfigFeatureSelect(cog))


class GeneralConfigView(discord.ui.View):
    """Config menu for general bot settings."""

    def __init__(self, cog: "ContentReviewCog") -> None:
        super().__init__(timeout=120)
        self.cog = cog

    @discord.ui.select(
        placeholder="Select a configuration action...",
        options=[
            discord.SelectOption(label="View Bot Admin Roles", value="view", emoji="📋"),
            discord.SelectOption(label="Add Bot Admin Role", value="add_role", emoji="➕"),
            discord.SelectOption(label="Remove Bot Admin Role", value="remove_role", emoji="➖"),
            discord.SelectOption(label="Clear All Bot Admin Roles", value="clear_roles", emoji="🗑️"),
        ],
    )
    async def action_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ) -> None:
        action = select.values[0]

        if action == "view":
            await self.cog._show_bot_admin_roles(interaction)
        elif action == "add_role":
            view = AddBotAdminRoleView(self.cog)
            await interaction.response.edit_message(
                content="Select a role to add as a bot admin role:", embed=None, view=view
            )
        elif action == "remove_role":
            await self.cog._show_remove_bot_admin_role_view(interaction)
        elif action == "clear_roles":
            await self.cog._clear_bot_admin_roles(interaction)


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


class ContentReviewConfigView(discord.ui.View):
    """Config menu for Content Review feature."""

    def __init__(self, cog: "ContentReviewCog") -> None:
        super().__init__(timeout=120)
        self.cog = cog

    @discord.ui.select(
        placeholder="Select a configuration action...",
        options=[
            discord.SelectOption(label="View Configuration", value="view", emoji="📋"),
            discord.SelectOption(label="Disable Content Review", value="disable", emoji="❌"),
            discord.SelectOption(label="Add Reviewer Role", value="add_role", emoji="➕"),
            discord.SelectOption(label="Remove Reviewer Role", value="remove_role", emoji="➖"),
            discord.SelectOption(label="Add Submission Field", value="add_field", emoji="📝"),
            discord.SelectOption(label="Remove Submission Field", value="remove_field", emoji="🗑️"),
            discord.SelectOption(label="Add Review Category", value="add_category", emoji="⭐"),
            discord.SelectOption(label="Remove Review Category", value="remove_category", emoji="🗑️"),
            discord.SelectOption(label="Customize Sticky Message", value="set_sticky", emoji="📌"),
            discord.SelectOption(label="Other Settings", value="set_settings", emoji="⚙️"),
            discord.SelectOption(label="Re-post Submit Button", value="repost", emoji="🔄"),
        ],
    )
    async def action_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ) -> None:
        action = select.values[0]

        if action == "view":
            await self.cog._show_config(interaction)
        elif action == "disable":
            await self.cog._disable_content_review(interaction)
        elif action == "add_role":
            view = AddRoleView(self.cog)
            await interaction.response.edit_message(
                content="Select a role to add as a reviewer:", embed=None, view=view
            )
        elif action == "remove_role":
            await self.cog._show_remove_role_view(interaction)
        elif action == "add_field":
            modal = AddFieldModal(self.cog)
            await interaction.response.send_modal(modal)
        elif action == "remove_field":
            await self.cog._show_remove_field_view(interaction)
        elif action == "add_category":
            modal = AddCategoryModal(self.cog)
            await interaction.response.send_modal(modal)
        elif action == "remove_category":
            await self.cog._show_remove_category_view(interaction)
        elif action == "set_sticky":
            modal = SetStickyModal(self.cog)
            await interaction.response.send_modal(modal)
        elif action == "set_settings":
            view = SettingsView(self.cog)
            await interaction.response.edit_message(
                content="Configure settings:", embed=None, view=view
            )
        elif action == "repost":
            await self.cog._repost_button(interaction)


class AlbionConfigView(discord.ui.View):
    """Config menu for Albion features."""

    def __init__(self, cog: "ContentReviewCog") -> None:
        super().__init__(timeout=120)
        self.cog = cog

    @discord.ui.select(
        placeholder="Select a configuration action...",
        options=[
            discord.SelectOption(label="View Status", value="view", emoji="📋"),
            discord.SelectOption(label="Enable Price Lookup", value="enable_prices", emoji="💰"),
            discord.SelectOption(label="Disable Price Lookup", value="disable_prices", emoji="❌"),
            discord.SelectOption(label="Enable Builds", value="enable_builds", emoji="⚔️"),
            discord.SelectOption(label="Disable Builds", value="disable_builds", emoji="❌"),
        ],
    )
    async def action_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ) -> None:
        action = select.values[0]

        if action == "view":
            await self.cog._show_albion_status(interaction)
        elif action == "enable_prices":
            await self.cog._enable_albion_feature(interaction, "prices")
        elif action == "disable_prices":
            await self.cog._disable_albion_feature(interaction, "prices")
        elif action == "enable_builds":
            await self.cog._enable_albion_feature(interaction, "builds")
        elif action == "disable_builds":
            await self.cog._disable_albion_feature(interaction, "builds")


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

        # Build options from existing fields
        options = [
            discord.SelectOption(label=f.label, value=f.id, description=f"ID: {f.id}")
            for f in fields
        ]
        self.field_select.options = options

    @discord.ui.select(placeholder="Select a field to remove...")
    async def field_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ) -> None:
        await self.cog._remove_field(interaction, select.values[0])


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
        # Parse score range
        try:
            parts = self.score_range.value.split("-")
            min_score = int(parts[0].strip())
            max_score = int(parts[1].strip()) if len(parts) > 1 else 5
        except (ValueError, IndexError):
            min_score, max_score = 1, 5

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

        options = [
            discord.SelectOption(label=c.name, value=c.id, description=f"ID: {c.id}")
            for c in categories
        ]
        self.category_select.options = options

    @discord.ui.select(placeholder="Select a category to remove...")
    async def category_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ) -> None:
        await self.cog._remove_category(interaction, select.values[0])


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

    def __init__(self, cog: "ContentReviewCog") -> None:
        super().__init__()
        self.cog = cog

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

    @discord.ui.select(
        placeholder="Select a setting to change...",
        options=[
            discord.SelectOption(label="Toggle DM on Complete", value="dm", emoji="📬"),
            discord.SelectOption(label="Toggle Leaderboard", value="leaderboard", emoji="🏆"),
            discord.SelectOption(label="Set Review Timeout", value="timeout", emoji="⏱️"),
        ],
    )
    async def setting_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ) -> None:
        setting = select.values[0]

        if setting == "dm":
            await self.cog._toggle_dm(interaction)
        elif setting == "leaderboard":
            await self.cog._toggle_leaderboard(interaction)
        elif setting == "timeout":
            modal = TimeoutModal(self.cog)
            await interaction.response.send_modal(modal)


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
        await self.cog._set_timeout(interaction, minutes)


class _CloseTicketConfirmView(discord.ui.View):
    """Confirmation dialog before closing/deleting a ticket channel."""

    def __init__(self, cog: "ContentReviewCog", submission: Submission) -> None:
        super().__init__(timeout=30)
        self.cog = cog
        self.submission = submission

    @discord.ui.button(label="Close & Delete", style=discord.ButtonStyle.danger, emoji="🔒")
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(content="Closing ticket…", view=None)
        await self.cog._close_ticket(interaction, self.submission)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(content="Cancelled.", view=None)
        self.stop()


class ContentReviewCog(commands.Cog):
    """Content review and feedback system."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._pending_reviews: dict[str, ReviewWizardView] = {}

    @property
    def firestore(self) -> FirestoreClient:
        return self.bot.lifeguard_firestore  # type: ignore[attr-defined]

    @staticmethod
    async def _respond(
        interaction: discord.Interaction,
        content: str,
        *,
        use_send: bool = False,
    ) -> None:
        """Send or edit an interaction response based on *use_send*.

        Centralises the send_message / edit_message branching so callers
        don't need to repeat the pattern.
        """
        if use_send:
            await interaction.response.send_message(content, ephemeral=True)
        else:
            await interaction.response.edit_message(content=content, embed=None, view=None)

    @staticmethod
    def _build_sticky_embed(config: ContentReviewConfig) -> discord.Embed:
        """Build the sticky submit-button embed from config."""
        embed = discord.Embed(
            title=config.sticky_title,
            description=config.sticky_description,
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="\U0001f4cb How it works",
            value=(
                f"1. Click **{config.sticky_button_label}** below\n"
                "2. Fill out the form with your content details\n"
                "3. A private ticket will be created for your review\n"
                "4. Reviewers will provide feedback in your ticket"
            ),
            inline=False,
        )
        embed.set_footer(
            text="\u26a0\ufe0f By submitting, you agree to receive constructive feedback on your content."
        )
        return embed

    def _user_can_manage_bot(self, interaction: discord.Interaction) -> bool:
        """Check if user has permission to manage bot settings.
        
        Returns True if:
        - User is a Discord administrator
        - User has one of the configured bot admin roles
        """
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return False
        
        # Discord admins always have access
        if interaction.user.guild_permissions.administrator:
            return True
        
        features = albion_repo.get_guild_features(self.firestore, interaction.guild.id)
        if not features or not features.bot_admin_role_ids:
            # No roles configured = only Discord admins can manage
            return False
        
        # Check if user has any of the allowed roles
        user_role_ids = {role.id for role in interaction.user.roles}
        return bool(user_role_ids & set(features.bot_admin_role_ids))

    async def cog_load(self) -> None:
        """Register persistent views on cog load."""
        # We handle persistent buttons via interaction handler
        LOGGER.info("Content Review cog loaded")

    # --- Main Interactive Commands ---

    # --- Main Interactive Commands ---

    @app_commands.command(
        name="enable-feature",
        description="Enable a bot feature",
    )
    @app_commands.describe(feature="The feature to enable")
    @app_commands.autocomplete(feature=feature_autocomplete)
    async def enable_feature_command(
        self,
        interaction: discord.Interaction,
        feature: str,
    ) -> None:
        """Enable a feature for this server."""
        if not interaction.guild:
            await interaction.response.send_message(_MSG_SERVER_ONLY, ephemeral=True)
            return

        if not self._user_can_manage_bot(interaction):
            await interaction.response.send_message(
                _MSG_NO_PERMISSION, ephemeral=True
            )
            return

        if not _is_valid_feature(feature):
            await interaction.response.send_message(
                f"Unknown feature: `{feature}`. Use autocomplete to select a valid feature.",
                ephemeral=True,
            )
            return

        # Features requiring setup show a wizard view
        if _feature_requires_setup(feature) and feature == "content_review":
                view = ContentReviewSetupView(self)
                embed = discord.Embed(
                    title="📝 Content Review Setup",
                    description=(
                        "Select the **ticket category** where review channels will be created.\n\n"
                        "The submit button will be posted in the current channel."
                    ),
                    color=discord.Color.blue(),
                )
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
                return

        # Simple features enable directly
        if feature == "time_impersonator":
            await self._enable_time_impersonator(interaction, use_send=True)
        elif feature == "albion_prices":
            await self._enable_albion_feature(interaction, "prices", use_send=True)
        elif feature == "albion_builds":
            await self._enable_albion_feature(interaction, "builds", use_send=True)

    @app_commands.command(
        name="disable-feature",
        description="Disable a bot feature",
    )
    @app_commands.describe(feature="The feature to disable")
    @app_commands.autocomplete(feature=feature_autocomplete)
    async def disable_feature_command(
        self,
        interaction: discord.Interaction,
        feature: str,
    ) -> None:
        """Disable a feature for this server."""
        if not interaction.guild:
            await interaction.response.send_message(_MSG_SERVER_ONLY, ephemeral=True)
            return

        if not self._user_can_manage_bot(interaction):
            await interaction.response.send_message(
                _MSG_NO_PERMISSION, ephemeral=True
            )
            return

        if not _is_valid_feature(feature):
            await interaction.response.send_message(
                f"Unknown feature: `{feature}`. Use autocomplete to select a valid feature.",
                ephemeral=True,
            )
            return

        if feature == "content_review":
            await self._disable_content_review_direct(interaction)
        elif feature == "time_impersonator":
            await self._disable_time_impersonator_direct(interaction)
        elif feature == "albion_prices":
            await self._disable_albion_feature_direct(interaction, "prices")
        elif feature == "albion_builds":
            await self._disable_albion_feature_direct(interaction, "builds")

    @app_commands.command(
        name="config",
        description="Configure bot settings",
    )
    async def config_command(self, interaction: discord.Interaction) -> None:
        """Show configuration menu."""
        if not interaction.guild:
            await interaction.response.send_message(_MSG_SERVER_ONLY, ephemeral=True)
            return

        if not self._user_can_manage_bot(interaction):
            await interaction.response.send_message(
                _MSG_NO_PERMISSION, ephemeral=True
            )
            return

        embed = discord.Embed(
            title="⚙️ Configuration",
            description="Select a feature to configure from the dropdown below.",
            color=discord.Color.blue(),
        )
        view = ConfigFeatureSelectView(self)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # --- Helper Methods for Interactive Views ---

    async def _enable_content_review(
        self,
        interaction: discord.Interaction,
        ticket_category_partial: discord.abc.GuildChannel,
        reviewer_role: discord.Role | None,
    ) -> None:
        """Enable content review with the selected options."""
        if not interaction.guild:
            return

        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.edit_message(
                content="Please run this command in a text channel.",
                embed=None,
                view=None,
            )
            return

        # Resolve the partial channel to actual category
        ticket_category = interaction.guild.get_channel(ticket_category_partial.id)
        if not ticket_category or not isinstance(ticket_category, discord.CategoryChannel):
            await interaction.response.edit_message(
                content="❌ Could not find that category.",
                embed=None,
                view=None,
            )
            return

        # Check bot permissions in the category
        bot_permissions = ticket_category.permissions_for(interaction.guild.me)
        if not bot_permissions.manage_channels:
            await interaction.response.edit_message(
                content=f"❌ I need **Manage Channels** permission in {ticket_category.mention}.",
                embed=None,
                view=None,
            )
            return

        await interaction.response.edit_message(
            content="Setting up content review...", embed=None, view=None
        )

        # Get or create config with defaults
        config = repo.get_or_create_config(self.firestore, interaction.guild.id)

        # Update with current settings and enable
        config.enabled = True
        config.submission_channel_id = interaction.channel.id
        config.ticket_category_id = ticket_category.id

        if reviewer_role and reviewer_role.id not in config.reviewer_role_ids:
            config.reviewer_role_ids.append(reviewer_role.id)

        repo.save_config(self.firestore, config)

        # Send sticky message with submit button
        sticky_embed = self._build_sticky_embed(config)
        submit_button_view = SubmitButtonView(
            label=config.sticky_button_label,
            emoji=config.sticky_button_emoji,
        )
        sticky_msg = await interaction.channel.send(embed=sticky_embed, view=submit_button_view)
        
        # Save the message ID for later cleanup
        config.sticky_message_id = sticky_msg.id
        repo.save_config(self.firestore, config)

        reviewer_msg = f"\n• Reviewer role: {reviewer_role.mention}" if reviewer_role else ""
        await interaction.edit_original_response(
            content=(
                f"✅ **Content Review enabled!**\n\n"
                f"• Submit button posted in this channel\n"
                f"• Tickets will be created in {ticket_category.mention}"
                f"{reviewer_msg}\n\n"
                f"Use `/config` to customize settings."
            ),
        )

        LOGGER.info(
            "Content review enabled: guild=%s channel=%s category=%s",
            interaction.guild.id,
            interaction.channel.id,
            ticket_category.id,
        )

    async def _show_config(self, interaction: discord.Interaction) -> None:
        """Display the current configuration."""
        if not interaction.guild:
            return

        config = repo.get_config(self.firestore, interaction.guild.id)
        if not config:
            await interaction.response.edit_message(
                content=_MSG_NOT_CONFIGURED, embed=None, view=None
            )
            return

        embed = discord.Embed(
            title="📋 Content Review Configuration",
            color=discord.Color.blue(),
        )

        status = _STATUS_ENABLED if config.enabled else _STATUS_DISABLED
        embed.add_field(name="Status", value=status, inline=True)

        sub_ch = f"<#{config.submission_channel_id}>" if config.submission_channel_id else "Not set"
        cat_ch = f"<#{config.ticket_category_id}>" if config.ticket_category_id else "Not set"
        embed.add_field(name="Submit Channel", value=sub_ch, inline=True)
        embed.add_field(name="Ticket Category", value=cat_ch, inline=True)

        if config.reviewer_role_ids:
            roles = ", ".join(f"<@&{r}>" for r in config.reviewer_role_ids)
        else:
            roles = "None (anyone can review)"
        embed.add_field(name="Reviewer Roles", value=roles, inline=False)

        if config.submission_fields:
            fields_str = "\n".join(
                f"• **{f.label}** (`{f.id}`) - {f.field_type}"
                + (" *required*" if f.required else "")
                for f in config.submission_fields
            )
        else:
            fields_str = "None configured"
        embed.add_field(name="Submission Fields", value=fields_str, inline=False)

        if config.review_categories:
            cats_str = "\n".join(
                f"• **{c.name}** (`{c.id}`) - {c.min_score}-{c.max_score} scale"
                for c in config.review_categories
            )
        else:
            cats_str = "None configured"
        embed.add_field(name="Review Categories", value=cats_str, inline=False)

        settings = (
            f"• DM on complete: {'Yes' if config.dm_on_complete else 'No'}\n"
            f"• Leaderboard: {'Enabled' if config.leaderboard_enabled else 'Disabled'}\n"
            f"• Review timeout: {config.review_timeout_minutes} minutes"
        )
        embed.add_field(name="Settings", value=settings, inline=False)

        sticky = f"**Title:** {config.sticky_title}\n**Button:** {config.sticky_button_emoji} {config.sticky_button_label}"
        embed.add_field(name="Sticky Message", value=sticky, inline=False)

        await interaction.response.edit_message(embed=embed, view=None)

    async def _disable_content_review(self, interaction: discord.Interaction) -> None:
        """Disable content review (from config menu)."""
        if not interaction.guild:
            return

        config = repo.get_config(self.firestore, interaction.guild.id)
        if not config:
            await interaction.response.edit_message(
                content=_MSG_NOT_CONFIGURED, embed=None, view=None
            )
            return

        config.enabled = False
        repo.save_config(self.firestore, config)
        await interaction.response.edit_message(
            content="✅ Content review disabled.", embed=None, view=None
        )

    async def _disable_content_review_feature(
        self,
        interaction: discord.Interaction,
        *,
        use_send: bool = False,
    ) -> None:
        """Fully disable content review feature.
        
        Args:
            interaction: The Discord interaction.
            use_send: If True, use send_message. If False, use edit_message.
        """
        if not interaction.guild:
            return

        config = repo.get_config(self.firestore, interaction.guild.id)
        if not config or not config.enabled:
            await self._respond(interaction, "Content review is not enabled.", use_send=use_send)
            return

        await self._try_delete_sticky(interaction.guild, config)

        config.enabled = False
        config.sticky_message_id = None
        repo.save_config(self.firestore, config)

        await self._respond(
            interaction,
            "✅ **Content Review disabled!**\n\n"
            "The feature has been turned off and the submit button removed.\n"
            "Existing configuration is preserved. Use `/enable-feature` to re-enable it.",
            use_send=use_send,
        )
        LOGGER.info("Content review disabled: guild=%s", interaction.guild.id)

    @staticmethod
    async def _try_delete_sticky(
        guild: discord.Guild, config: ContentReviewConfig
    ) -> None:
        """Attempt to delete the sticky submit-button message, ignoring errors."""
        if not config.submission_channel_id or not config.sticky_message_id:
            return
        try:
            channel = guild.get_channel(config.submission_channel_id)
            if channel and isinstance(channel, discord.TextChannel):
                msg = await channel.fetch_message(config.sticky_message_id)
                await msg.delete()
        except (discord.NotFound, discord.Forbidden):
            pass

    async def _try_update_sticky(
        self, guild: discord.Guild, config: ContentReviewConfig
    ) -> bool:
        """Attempt to edit the live sticky message with current config.

        Returns True if the message was successfully updated.
        """
        if not config.submission_channel_id or not config.sticky_message_id:
            return False
        try:
            channel = guild.get_channel(config.submission_channel_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                return False

            msg = await channel.fetch_message(config.sticky_message_id)

            sticky_embed = self._build_sticky_embed(config)
            submit_button_view = SubmitButtonView(
                label=config.sticky_button_label,
                emoji=config.sticky_button_emoji,
            )
            await msg.edit(embed=sticky_embed, view=submit_button_view)
            return True
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return False

    async def _disable_content_review_direct(self, interaction: discord.Interaction) -> None:
        """Disable content review (direct command flow)."""
        await self._disable_content_review_feature(interaction, use_send=True)

    # --- Time Impersonator Helpers ---

    async def _enable_time_impersonator(
        self,
        interaction: discord.Interaction,
        *,
        use_send: bool = False,
    ) -> None:
        """Enable time impersonator feature.
        
        Args:
            interaction: The Discord interaction.
            use_send: If True, use send_message. If False, use edit_message.
        """
        if not interaction.guild:
            return

        from lifeguard.modules.time_impersonator import repo as ti_repo
        from lifeguard.modules.time_impersonator.config import TimeImpersonatorConfig

        config = TimeImpersonatorConfig(guild_id=interaction.guild.id, enabled=True)
        ti_repo.save_config(self.firestore, config)

        content = (
            "✅ **Time Impersonator enabled!**\n\n"
            "Users can now:\n"
            "• `/tz set` — Set their timezone\n"
            "• `/time` — Send messages with dynamic timestamps\n\n"
            "The bot needs **Manage Webhooks** permission in channels where `/time` is used."
        )
        await self._respond(interaction, content, use_send=use_send)

        LOGGER.info("Time Impersonator enabled: guild=%s", interaction.guild.id)

    async def _disable_time_impersonator(
        self,
        interaction: discord.Interaction,
        *,
        use_send: bool = False,
    ) -> None:
        """Disable time impersonator feature.
        
        Args:
            interaction: The Discord interaction.
            use_send: If True, use send_message. If False, use edit_message.
        """
        if not interaction.guild:
            return

        from lifeguard.modules.time_impersonator import repo as ti_repo
        from lifeguard.modules.time_impersonator.config import TimeImpersonatorConfig

        config = ti_repo.get_config(self.firestore, interaction.guild.id)
        if not config or not config.enabled:
            await self._respond(
                interaction, "Time Impersonator is not enabled.", use_send=use_send
            )
            return

        config = TimeImpersonatorConfig(guild_id=interaction.guild.id, enabled=False)
        ti_repo.save_config(self.firestore, config)

        await self._respond(
            interaction, "✅ **Time Impersonator disabled!**", use_send=use_send
        )

        LOGGER.info("Time Impersonator disabled: guild=%s", interaction.guild.id)

    async def _disable_time_impersonator_direct(self, interaction: discord.Interaction) -> None:
        """Disable time impersonator (direct command flow)."""
        await self._disable_time_impersonator(interaction, use_send=True)

    async def _disable_albion_feature_direct(
        self, interaction: discord.Interaction, feature: str
    ) -> None:
        """Disable an Albion feature (direct command flow)."""
        if not interaction.guild:
            return

        features = albion_repo.get_guild_features(self.firestore, interaction.guild.id)
        if not features:
            await interaction.response.send_message(
                "No Albion features are currently configured.", ephemeral=True
            )
            return

        if feature == "prices":
            if not features.albion_prices_enabled:
                await interaction.response.send_message(
                    f"{_FEATURE_ALBION_PRICES} is not currently enabled.", ephemeral=True
                )
                return
            features.albion_prices_enabled = False
            feature_name = _FEATURE_ALBION_PRICES
        else:
            if not features.albion_builds_enabled:
                await interaction.response.send_message(
                    f"{_FEATURE_ALBION_BUILDS} is not currently enabled.", ephemeral=True
                )
                return
            features.albion_builds_enabled = False
            feature_name = _FEATURE_ALBION_BUILDS

        albion_repo.save_guild_features(self.firestore, features)

        await interaction.response.send_message(
            f"✅ **{feature_name} disabled!**", ephemeral=True
        )
        LOGGER.info("Albion %s disabled: guild=%s", feature, interaction.guild.id)

    # --- Bot Admin Role Helpers ---

    async def _show_bot_admin_roles(self, interaction: discord.Interaction) -> None:
        """Show the current bot admin roles."""
        if not interaction.guild:
            return

        features = albion_repo.get_guild_features(self.firestore, interaction.guild.id)
        role_ids = features.bot_admin_role_ids if features else []

        if not role_ids:
            embed = discord.Embed(
                title="🛡️ Bot Admin Roles",
                description="No bot admin roles configured.\n\n**Only Discord admins can manage the bot.**",
                color=discord.Color.blue(),
            )
        else:
            role_mentions = []
            for role_id in role_ids:
                role = interaction.guild.get_role(role_id)
                if role:
                    role_mentions.append(role.mention)
                else:
                    role_mentions.append(f"Unknown ({role_id})")
            
            embed = discord.Embed(
                title="🛡️ Bot Admin Roles",
                description=(
                    "Users with these roles can use `/enable-feature`, `/disable-feature`, and `/config`:\n\n"
                    + "\n".join(f"• {r}" for r in role_mentions)
                ),
                color=discord.Color.blue(),
            )

        await interaction.response.edit_message(embed=embed, view=None)

    async def _add_bot_admin_role(
        self, interaction: discord.Interaction, role: discord.Role
    ) -> None:
        """Add a bot admin role."""
        if not interaction.guild:
            return

        features = albion_repo.get_or_create_guild_features(
            self.firestore, interaction.guild.id
        )

        if role.id in features.bot_admin_role_ids:
            await interaction.response.edit_message(
                content=f"{role.mention} is already a bot admin role.",
                embed=None,
                view=None,
            )
            return

        features.bot_admin_role_ids.append(role.id)
        albion_repo.save_guild_features(self.firestore, features)

        await interaction.response.edit_message(
            content=f"✅ Added {role.mention} as a bot admin role.",
            embed=None,
            view=None,
        )
        LOGGER.info("Added bot admin role %s: guild=%s", role.id, interaction.guild.id)

    async def _show_remove_bot_admin_role_view(
        self, interaction: discord.Interaction
    ) -> None:
        """Show the view to remove a bot admin role."""
        if not interaction.guild:
            return

        features = albion_repo.get_guild_features(self.firestore, interaction.guild.id)
        if not features or not features.bot_admin_role_ids:
            await interaction.response.edit_message(
                content="No bot admin roles configured.", embed=None, view=None
            )
            return

        view = RemoveBotAdminRoleView(self, features.bot_admin_role_ids)
        await interaction.response.edit_message(
            content="Select a role to remove:", embed=None, view=view
        )

    async def _remove_bot_admin_role(
        self, interaction: discord.Interaction, role: discord.Role
    ) -> None:
        """Remove a bot admin role."""
        if not interaction.guild:
            return

        features = albion_repo.get_guild_features(self.firestore, interaction.guild.id)
        if not features or role.id not in features.bot_admin_role_ids:
            await interaction.response.edit_message(
                content=f"{role.mention} is not a bot admin role.",
                embed=None,
                view=None,
            )
            return

        features.bot_admin_role_ids.remove(role.id)
        albion_repo.save_guild_features(self.firestore, features)

        await interaction.response.edit_message(
            content=f"✅ Removed {role.mention} from bot admin roles.",
            embed=None,
            view=None,
        )
        LOGGER.info("Removed bot admin role %s: guild=%s", role.id, interaction.guild.id)

    async def _clear_bot_admin_roles(self, interaction: discord.Interaction) -> None:
        """Clear all bot admin roles (only Discord admins can manage)."""
        if not interaction.guild:
            return

        features = albion_repo.get_guild_features(self.firestore, interaction.guild.id)
        if not features or not features.bot_admin_role_ids:
            await interaction.response.edit_message(
                content="No bot admin roles to clear.", embed=None, view=None
            )
            return

        features.bot_admin_role_ids = []
        albion_repo.save_guild_features(self.firestore, features)

        await interaction.response.edit_message(
            content="✅ Cleared all bot admin roles. Only Discord admins can manage the bot now.",
            embed=None,
            view=None,
        )
        LOGGER.info("Cleared bot admin roles: guild=%s", interaction.guild.id)

    # --- Albion Feature Helpers ---

    async def _show_albion_status(self, interaction: discord.Interaction) -> None:
        """Show the current status of Albion features."""
        if not interaction.guild:
            return

        features = albion_repo.get_guild_features(self.firestore, interaction.guild.id)

        prices_status = _STATUS_ENABLED if features and features.albion_prices_enabled else _STATUS_DISABLED
        builds_status = _STATUS_ENABLED if features and features.albion_builds_enabled else _STATUS_DISABLED

        embed = discord.Embed(
            title="⚔️ Albion Features Status",
            color=discord.Color.blue(),
        )
        embed.add_field(name="💰 Price Lookup", value=prices_status, inline=True)
        embed.add_field(name="⚔️ Builds", value=builds_status, inline=True)

        await interaction.response.edit_message(embed=embed, view=None)

    async def _enable_albion_feature(
        self,
        interaction: discord.Interaction,
        feature: str,
        *,
        use_send: bool = False,
    ) -> None:
        """Enable an Albion feature (prices or builds).

        Args:
            interaction: The Discord interaction.
            feature: Which feature to enable ("prices" or "builds").
            use_send: If True, use send_message. If False, use edit_message.
        """
        if not interaction.guild:
            return

        features = albion_repo.get_or_create_guild_features(
            self.firestore, interaction.guild.id
        )

        if feature == "prices":
            features.albion_prices_enabled = True
            feature_name = _FEATURE_ALBION_PRICES
        else:
            features.albion_builds_enabled = True
            feature_name = _FEATURE_ALBION_BUILDS

        albion_repo.save_guild_features(self.firestore, features)

        await self._respond(
            interaction,
            f"✅ **{feature_name} enabled!**\n\nUsers can now use the related commands.",
            use_send=use_send,
        )

        LOGGER.info(
            "Albion %s enabled: guild=%s", feature, interaction.guild.id
        )

    async def _disable_albion_feature(
        self, interaction: discord.Interaction, feature: str
    ) -> None:
        """Disable an Albion feature (prices or builds)."""
        if not interaction.guild:
            return

        features = albion_repo.get_guild_features(self.firestore, interaction.guild.id)
        if not features:
            await interaction.response.edit_message(
                content="No Albion features are currently enabled.",
                embed=None,
                view=None,
            )
            return

        if feature == "prices":
            if not features.albion_prices_enabled:
                await interaction.response.edit_message(
                    content=f"{_FEATURE_ALBION_PRICES} is not currently enabled.",
                    embed=None,
                    view=None,
                )
                return
            features.albion_prices_enabled = False
            feature_name = _FEATURE_ALBION_PRICES
        else:
            if not features.albion_builds_enabled:
                await interaction.response.edit_message(
                    content=f"{_FEATURE_ALBION_BUILDS} is not currently enabled.",
                    embed=None,
                    view=None,
                )
                return
            features.albion_builds_enabled = False
            feature_name = _FEATURE_ALBION_BUILDS

        albion_repo.save_guild_features(self.firestore, features)

        await interaction.response.edit_message(
            content=f"✅ **{feature_name} disabled!**",
            embed=None,
            view=None,
        )
        LOGGER.info(
            "Albion %s disabled: guild=%s", feature, interaction.guild.id
        )

    async def _show_remove_role_view(self, interaction: discord.Interaction) -> None:
        """Show the view to remove a reviewer role."""
        if not interaction.guild:
            return

        config = repo.get_config(self.firestore, interaction.guild.id)
        if not config or not config.reviewer_role_ids:
            await interaction.response.edit_message(
                content="No reviewer roles configured.", embed=None, view=None
            )
            return

        view = RemoveRoleView(self, config.reviewer_role_ids)
        await interaction.response.edit_message(
            content="Select a role to remove:", embed=None, view=view
        )

    async def _add_reviewer_role(
        self, interaction: discord.Interaction, role: discord.Role
    ) -> None:
        """Add a reviewer role."""
        if not interaction.guild:
            return

        config = repo.get_or_create_config(self.firestore, interaction.guild.id)
        if role.id in config.reviewer_role_ids:
            await interaction.response.edit_message(
                content=f"{role.mention} is already a reviewer role.",
                embed=None,
                view=None,
            )
            return

        config.reviewer_role_ids.append(role.id)
        repo.save_config(self.firestore, config)
        await interaction.response.edit_message(
            content=f"✅ Added {role.mention} as a reviewer role.",
            embed=None,
            view=None,
        )

    async def _remove_reviewer_role(
        self, interaction: discord.Interaction, role: discord.Role
    ) -> None:
        """Remove a reviewer role."""
        if not interaction.guild:
            return

        config = repo.get_config(self.firestore, interaction.guild.id)
        if not config or role.id not in config.reviewer_role_ids:
            await interaction.response.edit_message(
                content=f"{role.mention} is not a reviewer role.",
                embed=None,
                view=None,
            )
            return

        config.reviewer_role_ids.remove(role.id)
        repo.save_config(self.firestore, config)
        await interaction.response.edit_message(
            content=f"✅ Removed {role.mention} from reviewer roles.",
            embed=None,
            view=None,
        )

    async def _show_remove_field_view(self, interaction: discord.Interaction) -> None:
        """Show the view to remove a submission field."""
        if not interaction.guild:
            return

        config = repo.get_config(self.firestore, interaction.guild.id)
        if not config or not config.submission_fields:
            await interaction.response.edit_message(
                content="No submission fields configured.", embed=None, view=None
            )
            return

        view = RemoveFieldView(self, config.submission_fields)
        await interaction.response.edit_message(
            content="Select a field to remove:", embed=None, view=view
        )

    async def _add_field(
        self,
        interaction: discord.Interaction,
        field_id: str,
        label: str,
        field_type: str,
        placeholder: str,
        required: bool,
    ) -> None:
        """Add a submission field."""
        if not interaction.guild:
            return

        config = repo.get_or_create_config(self.firestore, interaction.guild.id)

        if any(f.id == field_id for f in config.submission_fields):
            await interaction.response.send_message(
                f"A field with ID `{field_id}` already exists.", ephemeral=True
            )
            return

        if len(config.submission_fields) >= 5:
            await interaction.response.send_message(
                "Maximum of 5 submission fields allowed (Discord modal limit).",
                ephemeral=True,
            )
            return

        new_field = SubmissionField(
            id=field_id,
            label=label,
            field_type=field_type,  # type: ignore
            required=required,
            placeholder=placeholder,
        )
        config.submission_fields.append(new_field)
        repo.save_config(self.firestore, config)

        await interaction.response.send_message(
            f"✅ Added field **{label}** (`{field_id}`).", ephemeral=True
        )

    async def _remove_field(
        self, interaction: discord.Interaction, field_id: str
    ) -> None:
        """Remove a submission field."""
        if not interaction.guild:
            return

        config = repo.get_config(self.firestore, interaction.guild.id)
        if not config:
            await interaction.response.edit_message(
                content=_MSG_NOT_CONFIGURED, embed=None, view=None
            )
            return

        original_count = len(config.submission_fields)
        config.submission_fields = [f for f in config.submission_fields if f.id != field_id]

        if len(config.submission_fields) == original_count:
            await interaction.response.edit_message(
                content=f"No field with ID `{field_id}` found.", embed=None, view=None
            )
            return

        repo.save_config(self.firestore, config)
        await interaction.response.edit_message(
            content=f"✅ Removed field `{field_id}`.", embed=None, view=None
        )

    async def _show_remove_category_view(self, interaction: discord.Interaction) -> None:
        """Show the view to remove a review category."""
        if not interaction.guild:
            return

        config = repo.get_config(self.firestore, interaction.guild.id)
        if not config or not config.review_categories:
            await interaction.response.edit_message(
                content="No review categories configured.", embed=None, view=None
            )
            return

        view = RemoveCategoryView(self, config.review_categories)
        await interaction.response.edit_message(
            content="Select a category to remove:", embed=None, view=view
        )

    async def _add_category(
        self,
        interaction: discord.Interaction,
        category_id: str,
        name: str,
        description: str,
        min_score: int,
        max_score: int,
    ) -> None:
        """Add a review category."""
        if not interaction.guild:
            return

        config = repo.get_or_create_config(self.firestore, interaction.guild.id)

        if any(c.id == category_id for c in config.review_categories):
            await interaction.response.send_message(
                f"A category with ID `{category_id}` already exists.", ephemeral=True
            )
            return

        new_cat = ReviewCategory(
            id=category_id,
            name=name,
            description=description,
            min_score=min_score,
            max_score=max_score,
        )
        config.review_categories.append(new_cat)
        repo.save_config(self.firestore, config)

        await interaction.response.send_message(
            f"✅ Added category **{name}** (`{category_id}`) with {min_score}-{max_score} scale.",
            ephemeral=True,
        )

    async def _remove_category(
        self, interaction: discord.Interaction, category_id: str
    ) -> None:
        """Remove a review category."""
        if not interaction.guild:
            return

        config = repo.get_config(self.firestore, interaction.guild.id)
        if not config:
            await interaction.response.edit_message(
                content=_MSG_NOT_CONFIGURED, embed=None, view=None
            )
            return

        original_count = len(config.review_categories)
        config.review_categories = [c for c in config.review_categories if c.id != category_id]

        if len(config.review_categories) == original_count:
            await interaction.response.edit_message(
                content=f"No category with ID `{category_id}` found.",
                embed=None,
                view=None,
            )
            return

        repo.save_config(self.firestore, config)
        await interaction.response.edit_message(
            content=f"✅ Removed category `{category_id}`.", embed=None, view=None
        )

    async def _set_sticky(
        self,
        interaction: discord.Interaction,
        title: str | None,
        description: str | None,
        button_label: str | None,
        button_emoji: str | None,
    ) -> None:
        """Update sticky message settings."""
        if not interaction.guild:
            return

        config = repo.get_or_create_config(self.firestore, interaction.guild.id)
        changes = []

        if title:
            config.sticky_title = title
            changes.append(f"Title: {title}")
        if description:
            config.sticky_description = description
            changes.append("Description updated")
        if button_label:
            config.sticky_button_label = button_label
            changes.append(f"Button label: {button_label}")
        if button_emoji:
            config.sticky_button_emoji = button_emoji
            changes.append(f"Button emoji: {button_emoji}")

        if not changes:
            await interaction.response.send_message(
                "No changes made (all fields were empty).", ephemeral=True
            )
            return

        repo.save_config(self.firestore, config)

        # Try to live-update the existing sticky message
        updated_live = await self._try_update_sticky(interaction.guild, config)
        repost_hint = (
            ""
            if updated_live
            else "\n\n💡 Use **Re-post Submit Button** in `/config` to update the live message."
        )

        await interaction.response.send_message(
            "✅ Updated sticky message:\n"
            + "\n".join(f"• {c}" for c in changes)
            + repost_hint,
            ephemeral=True,
        )

    async def _toggle_dm(self, interaction: discord.Interaction) -> None:
        """Toggle DM on complete setting."""
        if not interaction.guild:
            return

        config = repo.get_or_create_config(self.firestore, interaction.guild.id)
        config.dm_on_complete = not config.dm_on_complete
        repo.save_config(self.firestore, config)

        status = "enabled" if config.dm_on_complete else "disabled"
        await interaction.response.edit_message(
            content=f"✅ DM on complete: **{status}**", embed=None, view=None
        )

    async def _toggle_leaderboard(self, interaction: discord.Interaction) -> None:
        """Toggle leaderboard setting."""
        if not interaction.guild:
            return

        config = repo.get_or_create_config(self.firestore, interaction.guild.id)
        config.leaderboard_enabled = not config.leaderboard_enabled
        repo.save_config(self.firestore, config)

        status = "enabled" if config.leaderboard_enabled else "disabled"
        await interaction.response.edit_message(
            content=f"✅ Leaderboard: **{status}**", embed=None, view=None
        )

    async def _set_timeout(self, interaction: discord.Interaction, minutes: int) -> None:
        """Set review timeout."""
        if not interaction.guild:
            return

        config = repo.get_or_create_config(self.firestore, interaction.guild.id)
        config.review_timeout_minutes = minutes
        repo.save_config(self.firestore, config)

        await interaction.response.send_message(
            f"✅ Review timeout set to **{minutes} minutes**.", ephemeral=True
        )

    async def _repost_button(self, interaction: discord.Interaction) -> None:
        """Re-post the submit button in the current channel."""
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.edit_message(
                content="Use this in a text channel.", embed=None, view=None
            )
            return

        config = repo.get_config(self.firestore, interaction.guild.id)
        if not config or not config.enabled:
            await interaction.response.edit_message(
                content="Content review is not enabled.", embed=None, view=None
            )
            return

        await interaction.response.edit_message(
            content="Posting submit button...", embed=None, view=None
        )

        config.submission_channel_id = interaction.channel.id
        repo.save_config(self.firestore, config)

        sticky_embed = self._build_sticky_embed(config)
        submit_button_view = SubmitButtonView(
            label=config.sticky_button_label,
            emoji=config.sticky_button_emoji,
        )
        await interaction.channel.send(embed=sticky_embed, view=submit_button_view)
        await interaction.edit_original_response(content="✅ Submit button posted!")

    # --- User Commands ---

    @app_commands.command(name="submit", description="Submit content for review")
    @require_content_review()
    async def submit_command(self, interaction: discord.Interaction) -> None:
        """Open the submission modal."""
        if not interaction.guild:
            await interaction.response.send_message(
                _MSG_GUILD_ONLY, ephemeral=True
            )
            return

        config = repo.get_config(self.firestore, interaction.guild.id)
        # Config is guaranteed to exist by the decorator

        if not config.submission_fields:
            await interaction.response.send_message(
                "No submission fields configured. Please contact an administrator.",
                ephemeral=True,
            )
            return

        async def on_submit(
            modal_interaction: discord.Interaction, field_values: dict[str, str]
        ) -> None:
            await self._handle_submission(modal_interaction, config, field_values)

        modal = SubmissionModal(config, on_submit)
        await interaction.response.send_modal(modal)

    async def _handle_submission(
        self,
        interaction: discord.Interaction,
        config: ContentReviewConfig,
        field_values: dict[str, str],
    ) -> None:
        """Process a submitted form by creating a ticket channel."""
        if not interaction.guild:
            return

        # Check ticket category is configured
        if not config.ticket_category_id:
            await interaction.response.send_message(
                "No ticket category configured. Please contact an administrator.",
                ephemeral=True,
            )
            return

        category = interaction.guild.get_channel(config.ticket_category_id)
        if not category or not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message(
                "Ticket category not found. Please contact an administrator.",
                ephemeral=True,
            )
            return

        # Defer while we create the ticket
        await interaction.response.defer(ephemeral=True)

        # Generate a unique ticket name using a short timestamp suffix
        short_id = f"{int(datetime.now(timezone.utc).timestamp()) % 100_000:05d}"
        ticket_name = f"review-{interaction.user.name[:20]}-{short_id}"

        # Build permission overwrites for the ticket channel
        overwrites: dict[discord.Role | discord.Member, discord.PermissionOverwrite] = {
            interaction.guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            ),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            ),
            interaction.guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                read_message_history=True,
            ),
        }

        # Add reviewer roles
        for role_id in config.reviewer_role_ids:
            role = interaction.guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                )

        try:
            # Create the ticket channel
            ticket_channel = await interaction.guild.create_text_channel(
                name=ticket_name,
                category=category,
                overwrites=overwrites,
                reason=f"Content review submission by {interaction.user}",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to create channels. "
                "Please ensure I have the Manage Channels permission.",
                ephemeral=True,
            )
            return
        except discord.HTTPException as e:
            LOGGER.error("Failed to create ticket channel: %s", e)
            await interaction.followup.send(
                "❌ Failed to create ticket channel. Please try again.",
                ephemeral=True,
            )
            return

        # Create submission record
        submission = Submission(
            id="",  # Will be generated
            guild_id=interaction.guild.id,
            channel_id=ticket_channel.id,
            message_id=0,  # Updated after posting
            submitter_id=interaction.user.id,
            fields=field_values,
            status="pending",
        )

        submission_id = repo.create_submission(self.firestore, submission)
        submission.id = submission_id

        # Build and send embed to ticket channel
        embed = build_submission_embed(submission, config, interaction.user)
        view = StartReviewButton(submission_id)

        # Add custom_id with submission ID for persistence
        view.children[0].custom_id = f"content_review:start_review:{submission_id}"

        # Send welcome message first
        welcome_embed = discord.Embed(
            title="📋 Content Review Ticket",
            description=(
                f"Welcome {interaction.user.mention}!\n\n"
                "Your submission has been received. A reviewer will start "
                "the review process by clicking the button below.\n\n"
                "You'll be notified once the review is complete."
            ),
            color=discord.Color.blue(),
        )
        await ticket_channel.send(embed=welcome_embed)

        # Send the submission embed with review button
        message = await ticket_channel.send(embed=embed, view=view)

        # Update submission with message ID
        submission.message_id = message.id
        repo.update_submission(self.firestore, submission)

        await interaction.followup.send(
            f"✅ Your ticket has been created: {ticket_channel.mention}\n"
            "A reviewer will be with you shortly!",
            ephemeral=True,
        )

        LOGGER.info(
            "Created review ticket: channel=%s submission=%s user=%s",
            ticket_channel.id,
            submission_id,
            interaction.user.id,
        )

        # Add close ticket button
        close_view = CloseTicketButton(submission_id)
        await ticket_channel.send(
            "When the review is complete, use the button below to close this ticket:",
            view=close_view,
        )

    @staticmethod
    def _can_close_ticket(
        user: discord.Member, submission: Submission
    ) -> bool:
        """Check whether *user* is allowed to close *submission*'s ticket."""
        return (
            user.id == submission.submitter_id
            or user.id == submission.reviewer_id
            or user.guild_permissions.administrator
        )

    @app_commands.command(name="close-ticket", description="Close this review ticket")
    @require_content_review()
    async def close_ticket_command(self, interaction: discord.Interaction) -> None:
        """Close the current ticket channel."""
        if not interaction.guild or not interaction.channel:
            await interaction.response.send_message(
                _MSG_GUILD_ONLY, ephemeral=True
            )
            return

        # Find submission for this channel
        submission = repo.get_submission_by_channel(
            self.firestore, interaction.guild.id, interaction.channel.id
        )

        if not submission:
            await interaction.response.send_message(
                "This channel is not a review ticket.", ephemeral=True
            )
            return

        if not self._can_close_ticket(interaction.user, submission):  # type: ignore[arg-type]
            await interaction.response.send_message(
                "Only the submitter, reviewer, or an admin can close this ticket.",
                ephemeral=True,
            )
            return

        await self._confirm_and_close_ticket(interaction, submission)

    async def _confirm_and_close_ticket(
        self, interaction: discord.Interaction, submission: Submission
    ) -> None:
        """Show a confirmation prompt before closing the ticket."""
        view = _CloseTicketConfirmView(self, submission)
        await interaction.response.send_message(
            "⚠️ **This will permanently close and delete this ticket channel.**\n"
            "Are you sure?",
            view=view,
            ephemeral=True,
        )

    async def _close_ticket(
        self, interaction: discord.Interaction, submission: Submission
    ) -> None:
        """Close a ticket channel (called after confirmation)."""
        if not interaction.guild or not isinstance(
            interaction.channel, discord.TextChannel
        ):
            return

        # Update submission status
        submission.status = "closed"
        repo.update_submission(self.firestore, submission)

        # Send closing message
        close_embed = discord.Embed(
            title="🔒 Ticket Closed",
            description="This ticket has been closed. The channel will be deleted shortly.",
            color=discord.Color.orange(),
        )
        await interaction.channel.send(embed=close_embed)

        # Delete channel after a short delay (allow reading the close message)
        await asyncio.sleep(5)

        try:
            await interaction.channel.delete(reason="Review ticket closed")
        except discord.HTTPException as e:
            LOGGER.error("Failed to delete ticket channel: %s", e)

    @app_commands.command(name="leaderboard", description="View reviewer rankings")
    @require_content_review()
    async def leaderboard_command(self, interaction: discord.Interaction) -> None:
        """Display the reviewer leaderboard."""
        if not interaction.guild:
            await interaction.response.send_message(
                _MSG_GUILD_ONLY, ephemeral=True
            )
            return

        config = repo.get_config(self.firestore, interaction.guild.id)
        if not config.leaderboard_enabled:
            await interaction.response.send_message(
                "Leaderboard is not enabled in this server.", ephemeral=True
            )
            return

        profiles = repo.get_leaderboard(self.firestore, interaction.guild.id)
        embed = build_leaderboard_embed(profiles, interaction.guild)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="review-profile", description="View your review stats")
    @app_commands.describe(user="User to view profile for (defaults to yourself)")
    @require_content_review()
    async def profile_command(
        self,
        interaction: discord.Interaction,
        user: discord.User | None = None,
    ) -> None:
        """View a user's review profile."""
        if not interaction.guild:
            await interaction.response.send_message(
                _MSG_GUILD_ONLY, ephemeral=True
            )
            return

        target_user = user or interaction.user
        config = repo.get_config(self.firestore, interaction.guild.id)

        profile = repo.get_profile(self.firestore, interaction.guild.id, target_user.id)
        if not profile:
            await interaction.response.send_message(
                f"{target_user.display_name} has no review profile yet.",
                ephemeral=True,
            )
            return

        embed = build_profile_embed(profile, config, target_user)
        await interaction.response.send_message(embed=embed)

    # --- Interaction Handler for Persistent Buttons ---

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        """Handle persistent button interactions."""
        if interaction.type != discord.InteractionType.component:
            return

        custom_id = interaction.data.get("custom_id", "")
        
        # Handle submit button from sticky message
        if custom_id == "content_review:submit_content":
            await self._handle_submit_button(interaction)
            return

        # Handle start review button
        if custom_id.startswith("content_review:start_review:"):
            submission_id = custom_id.split(":")[-1]
            await self._start_review(interaction, submission_id)
            return

        # Handle close ticket button
        if custom_id.startswith("content_review:close_ticket:"):
            submission_id = custom_id.split(":")[-1]
            await self._handle_close_button(interaction, submission_id)

    async def _handle_close_button(
        self, interaction: discord.Interaction, submission_id: str
    ) -> None:
        """Handle the close ticket button."""
        if not interaction.guild:
            return

        submission = repo.get_submission(self.firestore, submission_id)
        if not submission:
            await interaction.response.send_message(
                "Submission not found.", ephemeral=True
            )
            return

        if not self._can_close_ticket(interaction.user, submission):  # type: ignore[arg-type]
            await interaction.response.send_message(
                "Only the submitter, reviewer, or an admin can close this ticket.",
                ephemeral=True,
            )
            return

        await self._confirm_and_close_ticket(interaction, submission)

    async def _handle_submit_button(self, interaction: discord.Interaction) -> None:
        """Handle the submit button from sticky message."""
        if not interaction.guild:
            await interaction.response.send_message(
                "This can only be used in a server.", ephemeral=True
            )
            return

        config = repo.get_config(self.firestore, interaction.guild.id)
        if not config or not config.enabled:
            await interaction.response.send_message(
                "Content review is not enabled in this server.", ephemeral=True
            )
            return

        if not config.submission_fields:
            await interaction.response.send_message(
                "No submission fields configured.", ephemeral=True
            )
            return

        async def on_submit(
            modal_interaction: discord.Interaction, field_values: dict[str, str]
        ) -> None:
            await self._handle_submission(modal_interaction, config, field_values)

        modal = SubmissionModal(config, on_submit)
        await interaction.response.send_modal(modal)

    async def _start_review(
        self, interaction: discord.Interaction, submission_id: str
    ) -> None:
        """Start the review wizard for a submission."""
        if not interaction.guild:
            return

        # Get config and submission
        config = repo.get_config(self.firestore, interaction.guild.id)
        if not config:
            await interaction.response.send_message(
                "Content review is not configured.", ephemeral=True
            )
            return

        # Check if user has reviewer role
        if config.reviewer_role_ids:
            member = interaction.guild.get_member(interaction.user.id)
            if not member:
                # Fetch from API if not cached
                try:
                    member = await interaction.guild.fetch_member(interaction.user.id)
                except discord.NotFound:
                    await interaction.response.send_message(
                        "Could not verify your roles.", ephemeral=True
                    )
                    return

            has_role = any(
                role.id in config.reviewer_role_ids for role in member.roles
            )
            if not has_role:
                await interaction.response.send_message(
                    "You don't have permission to review submissions.",
                    ephemeral=True,
                )
                return

        submission = repo.get_submission(self.firestore, submission_id)
        if not submission:
            await interaction.response.send_message(
                "Submission not found.", ephemeral=True
            )
            return

        if submission.status == "completed":
            await interaction.response.send_message(
                "This submission has already been reviewed.", ephemeral=True
            )
            return

        # Check if user is reviewing their own submission
        if submission.submitter_id == interaction.user.id:
            await interaction.response.send_message(
                "You cannot review your own submission.", ephemeral=True
            )
            return

        # Create wizard
        async def on_publish(draft: DraftReview) -> None:
            await self._publish_review(interaction, config, submission, draft)

        wizard = ReviewWizardView(
            config=config,
            submission=submission,
            reviewer_id=interaction.user.id,
            on_publish_callback=on_publish,
            timeout=config.review_timeout_minutes * 60,
        )

        embed = wizard.build_embed()
        await interaction.response.send_message(embed=embed, view=wizard, ephemeral=True)

        # Track the wizard
        key = f"{interaction.user.id}:{submission_id}"
        self._pending_reviews[key] = wizard

    async def _publish_review(
        self,
        interaction: discord.Interaction,
        config: ContentReviewConfig,
        submission: Submission,
        draft: DraftReview,
    ) -> None:
        """Publish a completed review."""
        if not interaction.guild:
            return

        now = datetime.now(timezone.utc)

        # Create review record
        review = ReviewSession(
            id="",
            submission_id=submission.id,
            guild_id=submission.guild_id,
            reviewer_id=draft.reviewer_id,
            submitter_id=draft.submitter_id,
            scores=draft.scores,
            notes=draft.notes,
            created_at=draft.created_at,
            completed_at=now,
        )

        repo.create_review(self.firestore, review)

        # Update submission status
        submission.status = "completed"
        submission.reviewer_id = draft.reviewer_id
        repo.update_submission(self.firestore, submission)

        # Update user profiles
        submitter_profile = repo.get_or_create_profile(
            self.firestore, submission.guild_id, submission.submitter_id
        )
        submitter_profile.update_with_review(review)
        repo.save_profile(self.firestore, submitter_profile)

        reviewer_profile = repo.get_or_create_profile(
            self.firestore, submission.guild_id, draft.reviewer_id
        )
        reviewer_profile.total_reviews_given += 1
        repo.save_profile(self.firestore, reviewer_profile)

        # Get users for embed
        reviewer = interaction.user
        submitter = await self.bot.fetch_user(submission.submitter_id)

        # Build and send public review embed
        review_embed = build_review_embed(review, config, reviewer, submitter)

        # Reply to original submission message
        channel = interaction.guild.get_channel(submission.channel_id)
        if channel and isinstance(channel, discord.TextChannel):
            try:
                original_msg = await channel.fetch_message(submission.message_id)
                await original_msg.reply(embed=review_embed)
            except discord.NotFound:
                await channel.send(embed=review_embed)

        # DM submitter if enabled
        if config.dm_on_complete:
            try:
                await submitter.send(
                    content=f"Your submission in **{interaction.guild.name}** has been reviewed!",
                    embed=review_embed,
                )
            except discord.Forbidden:
                pass  # User has DMs disabled

        # Update the wizard message
        try:
            await interaction.edit_original_response(
                content="✅ Review published successfully!",
                embed=None,
                view=None,
            )
        except Exception:
            pass

        # Clean up tracking
        key = f"{interaction.user.id}:{submission.id}"
        self._pending_reviews.pop(key, None)

        LOGGER.info(
            "Review published: submission=%s reviewer=%s",
            submission.id,
            draft.reviewer_id,
        )

    # --- Error Handler ---

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        """Handle errors from app commands in this cog."""
        if isinstance(error, FeatureDisabledError):
            await interaction.response.send_message(
                f"❌ {error.feature_name} is not enabled in this server.\n"
                "An admin can enable it using `/enable-feature`.",
                ephemeral=True,
            )
            return
        # Re-raise other errors for global handler
        raise error


async def setup(bot: commands.Bot) -> None:
    """Setup function for loading as an extension."""
    await bot.add_cog(ContentReviewCog(bot))
