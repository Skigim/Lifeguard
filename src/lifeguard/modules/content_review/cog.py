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
from lifeguard.modules.content_review.views.config_ui import (
    BackToContentReviewView,
    ContentReviewConfigView,
    EditFormMenuView,
    RemoveCategoryView,
    RemoveFieldView,
    RemoveRoleView,
    ReviewerRolesMenuView,
    SettingsView,
    StickyConfigMenuView,
)
from lifeguard.modules.content_review.views.submission_modal import SubmissionModal
from lifeguard.modules.content_review.sticky_service import (
    post_sticky_message,
    sync_sticky_message,
    try_delete_sticky,
)
from lifeguard.exceptions import FeatureDisabledError

if TYPE_CHECKING:
    from google.cloud.firestore import Client as FirestoreClient

LOGGER = logging.getLogger(__name__)

# --- Common Response Strings ---
_MSG_GUILD_ONLY = "This command can only be used in a server."
_MSG_NOT_CONFIGURED = "Not configured."
_STATUS_ENABLED = "✅ Enabled"
_STATUS_DISABLED = "❌ Disabled"
_FEATURE_CONTENT_REVIEW = "Content Review"

_ALLOWED_FIELD_TYPES = frozenset({"short_text", "paragraph", "url"})


# --- Feature Check Decorators ---


def require_content_review():
    """Check that content review is enabled for this guild."""

    async def predicate(
        interaction: discord.Interaction,
    ) -> bool:  # NOSONAR - discord.py requires async
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


class _CloseTicketConfirmView(discord.ui.View):
    """Confirmation dialog before closing/deleting a ticket channel."""

    def __init__(self, cog: "ContentReviewCog", submission: Submission) -> None:
        super().__init__(timeout=30)
        self.cog = cog
        self.submission = submission

    @discord.ui.button(
        label="Close & Delete", style=discord.ButtonStyle.danger, emoji="🔒"
    )
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
        """Send or edit an interaction response based on *use_send*."""
        if use_send:
            await interaction.response.send_message(content, ephemeral=True)
        else:
            await interaction.response.edit_message(
                content=content, embed=None, view=None
            )

    @staticmethod
    def _extract_discord_id(value: str) -> int | None:
        """Extract a Discord snowflake from raw text or mention syntax."""
        digits = "".join(ch for ch in value if ch.isdigit())
        if not digits:
            return None
        return int(digits)

    def _resolve_role_from_input(
        self, guild: discord.Guild, value: str
    ) -> discord.Role | None:
        """Resolve a role from a role ID or mention string."""
        role_id = self._extract_discord_id(value)
        if role_id is None:
            return None
        return guild.get_role(role_id)

    def _resolve_category_from_input(
        self, guild: discord.Guild, value: str
    ) -> discord.CategoryChannel | None:
        """Resolve a category from a channel ID or mention string."""
        category_id = self._extract_discord_id(value)
        if category_id is None:
            return None
        channel = guild.get_channel(category_id)
        if isinstance(channel, discord.CategoryChannel):
            return channel
        return None

    @staticmethod
    def _resolve_reviewer_roles(
        guild: discord.Guild, config: ContentReviewConfig
    ) -> list[discord.Role]:
        """Resolve configured reviewer role IDs to existing role objects."""
        reviewer_roles: list[discord.Role] = []
        for role_id in config.reviewer_role_ids:
            role = guild.get_role(role_id)
            if role is not None:
                reviewer_roles.append(role)
        return reviewer_roles

    async def cog_load(self) -> None:
        """Register persistent views on cog load."""
        # Register a StartReviewButton with the base custom_id so discord.py
        # dispatches interactions for all dynamic IDs sharing this prefix.
        self.bot.add_view(StartReviewButton(""))
        # CloseTicketButton uses dynamic IDs handled by on_interaction.
        self.bot.add_view(CloseTicketButton(""))
        LOGGER.info("Content Review cog loaded")

    # --- Config Menu Navigation (called by ConfigCog) ---

    async def _show_content_review_config(
        self, interaction: discord.Interaction
    ) -> None:
        """Show the Content Review config sub-menu.

        This is the entry point called by ConfigCog when navigating to
        the Content Review section.
        """
        embed = discord.Embed(
            title="📝 Content Review Config",
            description="Use the buttons below to configure Content Review.",
            color=discord.Color.blue(),
        )
        await interaction.response.edit_message(
            embed=embed,
            view=ContentReviewConfigView(self),
            content=None,
        )

    async def _show_sticky_menu(self, interaction: discord.Interaction) -> None:
        """Show nested sticky message configuration menu."""
        embed = discord.Embed(
            title="📌 Sticky Message Menu",
            description="Edit or repost the submit-button sticky message.",
            color=discord.Color.blue(),
        )
        await interaction.response.edit_message(
            embed=embed,
            view=StickyConfigMenuView(self),
            content=None,
        )

    async def _show_reviewer_roles_menu(self, interaction: discord.Interaction) -> None:
        """Show nested reviewer roles management menu."""
        embed = discord.Embed(
            title="👥 Review Roles Menu",
            description="Add or remove roles that can review submissions.",
            color=discord.Color.blue(),
        )
        await interaction.response.edit_message(
            embed=embed,
            view=ReviewerRolesMenuView(self),
            content=None,
        )

    async def _show_form_editor_menu(self, interaction: discord.Interaction) -> None:
        """Show nested form editor menu."""
        embed = discord.Embed(
            title="🧩 Edit Form Menu",
            description="Manage form fields, review categories, and ticket category.",
            color=discord.Color.blue(),
        )
        await interaction.response.edit_message(
            embed=embed,
            view=EditFormMenuView(self),
            content=None,
        )

    # --- Content Review Config Helpers ---

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

        sub_ch = (
            f"<#{config.submission_channel_id}>"
            if config.submission_channel_id
            else "Not set"
        )
        cat_ch = (
            f"<#{config.ticket_category_id}>"
            if config.ticket_category_id
            else "Not set"
        )
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

        await interaction.response.edit_message(
            embed=embed, view=BackToContentReviewView(self)
        )

    # --- Enable / Disable ---

    async def _enable_content_review(
        self,
        interaction: discord.Interaction,
        ticket_category_partial: discord.abc.GuildChannel,
        reviewer_role: discord.Role | None,
        *,
        use_send: bool = False,
    ) -> None:
        """Enable content review with the selected options."""
        if not interaction.guild:
            return

        if not isinstance(interaction.channel, discord.TextChannel):
            await self._respond(
                interaction,
                "Please run this command in a text channel.",
                use_send=use_send,
            )
            return

        # Resolve the partial channel to actual category
        ticket_category = interaction.guild.get_channel(ticket_category_partial.id)
        if not ticket_category or not isinstance(
            ticket_category, discord.CategoryChannel
        ):
            await self._respond(
                interaction,
                "❌ Could not find that category.",
                use_send=use_send,
            )
            return

        # Check bot permissions in the category
        bot_permissions = ticket_category.permissions_for(interaction.guild.me)
        if not bot_permissions.manage_channels:
            await self._respond(
                interaction,
                f"❌ I need **Manage Channels** permission in {ticket_category.mention}.",
                use_send=use_send,
            )
            return

        if not use_send:
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
        sticky_msg = await self._post_sticky_message(interaction.channel, config)

        # Save the message ID for later cleanup
        config.sticky_message_id = sticky_msg.id
        repo.save_config(self.firestore, config)

        reviewer_msg = (
            f"\n• Reviewer role: {reviewer_role.mention}" if reviewer_role else ""
        )
        success_message = (
            f"✅ **Content Review enabled!**\n\n"
            f"• Submit button posted in this channel\n"
            f"• Tickets will be created in {ticket_category.mention}"
            f"{reviewer_msg}\n\n"
            f"Use `/config` to customize settings."
        )

        if use_send:
            await interaction.response.send_message(success_message, ephemeral=True)
        else:
            await interaction.edit_original_response(content=success_message)

        LOGGER.info(
            "Content review enabled: guild=%s channel=%s category=%s",
            interaction.guild.id,
            interaction.channel.id,
            ticket_category.id,
        )

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
            await self._respond(
                interaction, "Content review is not enabled.", use_send=use_send
            )
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

    # --- Sticky Message Helpers ---

    async def _try_delete_sticky(
        self, guild: discord.Guild, config: ContentReviewConfig
    ) -> None:
        """Attempt to delete the sticky submit-button message, ignoring errors."""
        await try_delete_sticky(guild, config)

    async def _post_sticky_message(
        self, channel: discord.TextChannel, config: ContentReviewConfig
    ) -> discord.Message:
        """Post the sticky submit message and return it."""
        return await post_sticky_message(channel, config)

    async def _sync_sticky_message(
        self, guild: discord.Guild, config: ContentReviewConfig
    ) -> str:
        """Sync sticky message after config changes.

        Returns one of: "updated", "reposted", "failed".
        """
        return await sync_sticky_message(self.firestore, guild, config)

    # --- Reviewer Role Helpers ---

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
            content="Select a role to remove from reviewer roles:",
            embed=None,
            view=view,
        )

    async def _add_reviewer_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        *,
        use_send: bool = False,
    ) -> None:
        """Add a reviewer role."""
        if not interaction.guild:
            return

        config = repo.get_or_create_config(self.firestore, interaction.guild.id)
        if role.id in config.reviewer_role_ids:
            await self._respond(
                interaction,
                f"{role.mention} is already a reviewer role.",
                use_send=use_send,
            )
            return

        config.reviewer_role_ids.append(role.id)
        repo.save_config(self.firestore, config)
        if use_send:
            await self._respond(
                interaction,
                f"✅ Added {role.mention} as a reviewer role.",
                use_send=True,
            )
        else:
            await interaction.response.edit_message(
                content=f"✅ Added {role.mention} as a reviewer role.",
                embed=None,
                view=ReviewerRolesMenuView(self),
            )

    async def _remove_reviewer_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        *,
        use_send: bool = False,
    ) -> None:
        """Remove a reviewer role."""
        if not interaction.guild:
            return

        config = repo.get_config(self.firestore, interaction.guild.id)
        if not config or role.id not in config.reviewer_role_ids:
            await self._respond(
                interaction,
                f"{role.mention} is not a reviewer role.",
                use_send=use_send,
            )
            return

        config.reviewer_role_ids.remove(role.id)
        repo.save_config(self.firestore, config)
        if use_send:
            await self._respond(
                interaction,
                f"✅ Removed {role.mention} from reviewer roles.",
                use_send=True,
            )
        else:
            await interaction.response.edit_message(
                content=f"✅ Removed {role.mention} from reviewer roles.",
                embed=None,
                view=ReviewerRolesMenuView(self),
            )

    # --- Form Field Helpers ---

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
        field_ids = ", ".join(f.id for f in config.submission_fields)
        await interaction.response.edit_message(
            content=f"Enter the field ID to remove. Available IDs: {field_ids}",
            embed=None,
            view=view,
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

        if field_type not in _ALLOWED_FIELD_TYPES:
            await interaction.response.send_message(
                f"Invalid field type `{field_type}`. "
                f"Allowed: {', '.join(sorted(_ALLOWED_FIELD_TYPES))}.",
                ephemeral=True,
            )
            return

        new_field = SubmissionField(
            id=field_id,
            label=label,
            field_type=field_type,
            required=required,
            placeholder=placeholder,
        )
        config.submission_fields.append(new_field)
        repo.save_config(self.firestore, config)

        await interaction.response.send_message(
            f"✅ Added field **{label}** (`{field_id}`).", ephemeral=True
        )

    async def _remove_field(
        self,
        interaction: discord.Interaction,
        field_id: str,
        *,
        use_send: bool = False,
    ) -> None:
        """Remove a submission field."""
        if not interaction.guild:
            return

        config = repo.get_config(self.firestore, interaction.guild.id)
        if not config:
            await self._respond(interaction, _MSG_NOT_CONFIGURED, use_send=use_send)
            return

        original_count = len(config.submission_fields)
        config.submission_fields = [
            f for f in config.submission_fields if f.id != field_id
        ]

        if len(config.submission_fields) == original_count:
            await self._respond(
                interaction,
                f"No field with ID `{field_id}` found.",
                use_send=use_send,
            )
            return

        repo.save_config(self.firestore, config)
        if use_send:
            await self._respond(
                interaction,
                f"✅ Removed field `{field_id}`.",
                use_send=True,
            )
        else:
            await interaction.response.edit_message(
                content=f"✅ Removed field `{field_id}`.",
                embed=None,
                view=EditFormMenuView(self),
            )

    # --- Review Category Helpers ---

    async def _show_remove_category_view(
        self, interaction: discord.Interaction
    ) -> None:
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
        category_ids = ", ".join(c.id for c in config.review_categories)
        await interaction.response.edit_message(
            content=f"Enter the category ID to remove. Available IDs: {category_ids}",
            embed=None,
            view=view,
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

        if min_score > max_score:
            await interaction.response.send_message(
                f"min_score ({min_score}) must be <= max_score ({max_score}).",
                ephemeral=True,
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
        self,
        interaction: discord.Interaction,
        category_id: str,
        *,
        use_send: bool = False,
    ) -> None:
        """Remove a review category."""
        if not interaction.guild:
            return

        config = repo.get_config(self.firestore, interaction.guild.id)
        if not config:
            await self._respond(interaction, _MSG_NOT_CONFIGURED, use_send=use_send)
            return

        original_count = len(config.review_categories)
        config.review_categories = [
            c for c in config.review_categories if c.id != category_id
        ]

        if len(config.review_categories) == original_count:
            await self._respond(
                interaction,
                f"No category with ID `{category_id}` found.",
                use_send=use_send,
            )
            return

        repo.save_config(self.firestore, config)
        if use_send:
            await self._respond(
                interaction,
                f"✅ Removed category `{category_id}`.",
                use_send=True,
            )
        else:
            await interaction.response.edit_message(
                content=f"✅ Removed category `{category_id}`.",
                embed=None,
                view=EditFormMenuView(self),
            )

    # --- Ticket Category ---

    async def _set_ticket_category(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
        *,
        use_send: bool = False,
    ) -> None:
        """Set the ticket category used for new review tickets."""
        if not interaction.guild:
            return

        bot_member = interaction.guild.me
        has_manage_channels = (
            bot_member is not None
            and category.permissions_for(bot_member).manage_channels
        )
        if not has_manage_channels:
            await self._respond(
                interaction,
                f"❌ I need **Manage Channels** permission in {category.mention}.",
                use_send=use_send,
            )
            return

        config = repo.get_or_create_config(self.firestore, interaction.guild.id)
        config.ticket_category_id = category.id
        repo.save_config(self.firestore, config)

        if use_send:
            await self._respond(
                interaction,
                f"✅ Ticket category set to {category.mention}.",
                use_send=True,
            )
            return

        await interaction.response.edit_message(
            content=f"✅ Ticket category set to {category.mention}.",
            embed=None,
            view=EditFormMenuView(self),
        )

    # --- Sticky / Settings ---

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

        sync_result = await self._sync_sticky_message(interaction.guild, config)
        if sync_result == "updated":
            sync_note = "\n\n✅ Live sticky message updated in place."
        elif sync_result == "reposted":
            sync_note = "\n\n✅ Sticky message was missing, so a new one was posted automatically."
        else:
            sync_note = "\n\n💡 Use **Re-post Submit Button** in `/config` to update the live message."

        await interaction.response.send_message(
            "✅ Updated sticky message:\n"
            + "\n".join(f"• {c}" for c in changes)
            + sync_note,
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
            content=f"✅ DM on complete: **{status}**",
            embed=None,
            view=SettingsView(self),
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
            content=f"✅ Leaderboard: **{status}**",
            embed=None,
            view=SettingsView(self),
        )

    async def _set_timeout(
        self, interaction: discord.Interaction, minutes: int
    ) -> None:
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
        if not interaction.guild or not isinstance(
            interaction.channel, discord.TextChannel
        ):
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

        sticky_msg = await self._post_sticky_message(interaction.channel, config)
        config.sticky_message_id = sticky_msg.id
        repo.save_config(self.firestore, config)

        await interaction.edit_original_response(content="✅ Submit button posted!")

    # --- User Commands ---

    @app_commands.command(name="submit", description="Submit content for review")
    @require_content_review()
    async def submit_command(self, interaction: discord.Interaction) -> None:
        """Open the submission modal."""
        if not interaction.guild:
            await interaction.response.send_message(_MSG_GUILD_ONLY, ephemeral=True)
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

        reviewer_roles = self._resolve_reviewer_roles(interaction.guild, config)

        # Add reviewer roles
        for role in reviewer_roles:
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

        if reviewer_roles:
            reviewer_mentions = " ".join(role.mention for role in reviewer_roles)
            await ticket_channel.send(
                f"{reviewer_mentions} New content review ticket is ready.",
                allowed_mentions=discord.AllowedMentions(
                    roles=True,
                    users=False,
                    everyone=False,
                ),
            )

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
    def _can_close_ticket(user: discord.Member, submission: Submission) -> bool:
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
            await interaction.response.send_message(_MSG_GUILD_ONLY, ephemeral=True)
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

        submission.status = "closed"
        repo.update_submission(self.firestore, submission)

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
            await interaction.response.send_message(_MSG_GUILD_ONLY, ephemeral=True)
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
            await interaction.response.send_message(_MSG_GUILD_ONLY, ephemeral=True)
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

            has_role = any(role.id in config.reviewer_role_ids for role in member.roles)
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

        try:
            submission = repo.claim_submission_for_review(
                self.firestore,
                submission_id,
                interaction.user.id,
            )
        except repo.SubmissionNotFoundError:
            await interaction.response.send_message(
                "Submission not found.", ephemeral=True
            )
            return
        except repo.SubmissionAlreadyClaimedError:
            await interaction.response.send_message(
                "This submission was already claimed for review.", ephemeral=True
            )
            return

        wizard = ReviewWizardView(
            config=config,
            submission=submission,
            reviewer_id=interaction.user.id,
            on_publish_callback=on_publish,
            timeout=config.review_timeout_minutes * 60,
        )

        embed = wizard.build_embed()
        await interaction.response.send_message(
            embed=embed, view=wizard, ephemeral=True
        )

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
        try:
            submitter = await self.bot.fetch_user(submission.submitter_id)
        except discord.NotFound:
            LOGGER.warning(
                "Submitter user %s not found; skipping DM",
                submission.submitter_id,
            )
            submitter = None
        except discord.HTTPException:
            LOGGER.exception(
                "Failed to fetch submitter user %s",
                submission.submitter_id,
            )
            submitter = None

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
        if config.dm_on_complete and submitter is not None:
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
        except discord.Forbidden as exc:
            LOGGER.warning("No permission to update wizard message: %s", exc)
        except discord.HTTPException as exc:
            LOGGER.warning("Failed to update wizard message: %s", exc)

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
