"""Configuration Cog – owns /config, /enable-feature, /disable-feature.

This cog is the single owner of all cross-cutting configuration commands and
their supporting helpers.  Module-specific sub-menus delegate back to the
owning module's cog when needed (e.g. Content Review setup).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from lifeguard.cogs.config_views import (
    AlbionConfigView,
    BackToAlbionView,
    BackToGeneralView,
    ConfigFeatureSelectView,
    ContentReviewDisabledView,
    GeneralConfigView,
    RemoveBotAdminRoleView,
    TimeImpersonatorConfigView,
    VoiceLobbyConfigView,
)
from lifeguard.modules.albion import repo as albion_repo

if TYPE_CHECKING:
    from google.cloud.firestore import Client as FirestoreClient

LOGGER = logging.getLogger(__name__)

# --- Common Response Strings ---
_MSG_SERVER_ONLY = "Server only."
_MSG_NO_PERMISSION = "You don't have permission to manage bot settings."
_STATUS_ENABLED = "✅ Enabled"
_STATUS_DISABLED = "❌ Disabled"
_FEATURE_ALBION_PRICES = "Albion Price Lookup"
_FEATURE_ALBION_BUILDS = "Albion Builds"
_FEATURE_CONTENT_REVIEW = "Content Review"
_FEATURE_VOICE_LOBBY = "Voice Lobby"


# --- Feature Registry ---
FEATURES: list[tuple[str, str, str, bool]] = [
    (
        "content_review",
        "Content Review",
        "Review system with tickets, scoring, and leaderboards",
        True,
    ),
    (
        "time_impersonator",
        "Time Impersonator",
        "Send messages with dynamic Discord timestamps",
        False,
    ),
    (
        "voice_lobby",
        "Voice Lobby",
        "Temporary voice lobbies created from an entry channel",
        False,
    ),
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


class ConfigCog(commands.Cog):
    """Central configuration commands and cross-cutting config helpers."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @property
    def firestore(self) -> FirestoreClient:
        return self.bot.lifeguard_firestore  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

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

    def _user_can_manage_bot(self, interaction: discord.Interaction) -> bool:
        """Check if user has permission to manage bot settings."""
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return False

        if interaction.user.guild_permissions.administrator:
            return True

        features = albion_repo.get_guild_features(self.firestore, interaction.guild.id)
        if not features or not features.bot_admin_role_ids:
            return False

        user_role_ids = {role.id for role in interaction.user.roles}
        return bool(user_role_ids & set(features.bot_admin_role_ids))

    # ------------------------------------------------------------------
    # Slash commands
    # ------------------------------------------------------------------

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
            await interaction.response.send_message(_MSG_NO_PERMISSION, ephemeral=True)
            return

        if not _is_valid_feature(feature):
            await interaction.response.send_message(
                f"Unknown feature: `{feature}`. Use autocomplete to select a valid feature.",
                ephemeral=True,
            )
            return

        # Features requiring setup show a wizard view
        if _feature_requires_setup(feature) and feature == "content_review":
            cr_cog = self.bot.get_cog("ContentReviewCog")
            if not cr_cog:
                await interaction.response.send_message(
                    "Content Review module is not loaded.", ephemeral=True
                )
                return
            from lifeguard.modules.content_review.views.config_ui import (
                ContentReviewSetupView,
            )

            view = ContentReviewSetupView(cr_cog)
            embed = discord.Embed(
                title="📝 Content Review Setup",
                description=(
                    "Select the **ticket category** where review channels will be created.\n\n"
                    "The submit button will be posted in the current channel."
                ),
                color=discord.Color.blue(),
            )
            await interaction.response.send_message(
                embed=embed, view=view, ephemeral=True
            )
            return

        # Simple features enable directly
        if feature == "time_impersonator":
            await self._enable_time_impersonator(interaction, use_send=True)
        elif feature == "voice_lobby":
            await self._enable_voice_lobby(interaction, use_send=True)
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
            await interaction.response.send_message(_MSG_NO_PERMISSION, ephemeral=True)
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
        elif feature == "voice_lobby":
            await self._disable_voice_lobby_direct(interaction)
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
            await interaction.response.send_message(_MSG_NO_PERMISSION, ephemeral=True)
            return

        await self._show_config_home(interaction, use_send=True)

    # ------------------------------------------------------------------
    # Embed builders
    # ------------------------------------------------------------------

    @staticmethod
    def _build_config_home_embed() -> discord.Embed:
        return discord.Embed(
            title="⚙️ Configuration",
            description="Use the buttons below to configure bot features.",
            color=discord.Color.blue(),
        )

    @staticmethod
    def _build_general_embed() -> discord.Embed:
        return discord.Embed(
            title="⚙️ General Settings",
            description="Use the buttons below to configure general bot settings.",
            color=discord.Color.blue(),
        )

    @staticmethod
    def _build_albion_embed() -> discord.Embed:
        return discord.Embed(
            title="⚔️ Albion Config",
            description="Use the buttons below to configure Albion features.",
            color=discord.Color.blue(),
        )

    @staticmethod
    def _build_voice_lobby_embed() -> discord.Embed:
        return discord.Embed(
            title="🎧 Voice Lobby Config",
            description="Configure default temporary lobby options.",
            color=discord.Color.blue(),
        )

    # ------------------------------------------------------------------
    # Navigation helpers
    # ------------------------------------------------------------------

    async def _show_config_home(
        self, interaction: discord.Interaction, *, use_send: bool = False
    ) -> None:
        if use_send:
            await interaction.response.send_message(
                embed=self._build_config_home_embed(),
                view=ConfigFeatureSelectView(self),
                ephemeral=True,
            )
            return
        await interaction.response.edit_message(
            embed=self._build_config_home_embed(),
            view=ConfigFeatureSelectView(self),
            content=None,
        )

    async def _show_general_menu(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=self._build_general_embed(),
            view=GeneralConfigView(self),
            content=None,
        )

    async def _show_content_review_menu(self, interaction: discord.Interaction) -> None:
        """Navigate to the Content Review sub-menu.

        Delegates to ContentReviewCog for CR-specific config when enabled.
        """
        if not interaction.guild:
            return

        from lifeguard.modules.content_review import repo

        config = repo.get_config(self.firestore, interaction.guild.id)
        if not config or not config.enabled:
            embed = discord.Embed(
                title="📝 Content Review",
                description="Content Review is **not enabled**. Enable it to get started.",
                color=discord.Color.greyple(),
            )
            await interaction.response.edit_message(
                embed=embed,
                view=ContentReviewDisabledView(self),
                content=None,
            )
            return

        # Delegate to CR cog for the full config menu
        cr_cog = self.bot.get_cog("ContentReviewCog")
        if cr_cog:
            await cr_cog._show_content_review_config(interaction)
        else:
            await interaction.response.edit_message(
                content="Content Review module is not loaded.",
                embed=None,
                view=None,
            )

    async def _show_albion_menu(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=self._build_albion_embed(),
            view=AlbionConfigView(self),
            content=None,
        )

    async def _show_voice_lobby_menu(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=self._build_voice_lobby_embed(),
            view=VoiceLobbyConfigView(self),
            content=None,
        )

    async def _show_time_impersonator_menu(
        self, interaction: discord.Interaction
    ) -> None:
        embed = discord.Embed(
            title="🕐 Time Impersonator Config",
            description="Enable, disable, or view status of the Time Impersonator feature.",
            color=discord.Color.blue(),
        )
        await interaction.response.edit_message(
            embed=embed,
            view=TimeImpersonatorConfigView(self),
            content=None,
        )

    async def _show_time_impersonator_status(
        self, interaction: discord.Interaction
    ) -> None:
        if not interaction.guild:
            return

        from lifeguard.modules.time_impersonator import repo as ti_repo

        config = ti_repo.get_config(self.firestore, interaction.guild.id)
        status = _STATUS_ENABLED if config and config.enabled else _STATUS_DISABLED

        await interaction.response.edit_message(
            content=f"**Time Impersonator:** {status}",
            embed=None,
            view=TimeImpersonatorConfigView(self),
        )

    # ------------------------------------------------------------------
    # Time Impersonator enable/disable
    # ------------------------------------------------------------------

    async def _enable_time_impersonator(
        self,
        interaction: discord.Interaction,
        *,
        use_send: bool = False,
    ) -> None:
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

    async def _disable_time_impersonator_direct(
        self, interaction: discord.Interaction
    ) -> None:
        await self._disable_time_impersonator(interaction, use_send=True)

    # ------------------------------------------------------------------
    # Voice Lobby enable/disable + config helpers
    # ------------------------------------------------------------------

    async def _enable_voice_lobby(
        self,
        interaction: discord.Interaction,
        *,
        use_send: bool = False,
    ) -> None:
        if not interaction.guild:
            return

        from lifeguard.modules.voice_lobby import repo as voice_repo
        from lifeguard.modules.voice_lobby.config import VoiceLobbyConfig

        existing = voice_repo.get_config(self.firestore, interaction.guild.id)
        if existing is None:
            config = VoiceLobbyConfig(guild_id=interaction.guild.id, enabled=True)
        else:
            existing.enabled = True
            config = existing

        voice_repo.save_config(self.firestore, config)

        content = (
            f"✅ **{_FEATURE_VOICE_LOBBY} enabled!**\n\n"
            "Next step: open `/config` → **Voice Lobby** to set entry channel, defaults, and role rules."
        )
        await self._respond(interaction, content, use_send=use_send)

    async def _disable_voice_lobby(
        self,
        interaction: discord.Interaction,
        *,
        use_send: bool = False,
    ) -> None:
        if not interaction.guild:
            return

        from lifeguard.modules.voice_lobby import repo as voice_repo

        config = voice_repo.get_config(self.firestore, interaction.guild.id)
        if not config or not config.enabled:
            await self._respond(
                interaction,
                f"{_FEATURE_VOICE_LOBBY} is not enabled.",
                use_send=use_send,
            )
            return

        config.enabled = False
        voice_repo.save_config(self.firestore, config)

        await self._respond(
            interaction,
            f"✅ **{_FEATURE_VOICE_LOBBY} disabled!**",
            use_send=use_send,
        )

    async def _disable_voice_lobby_direct(
        self, interaction: discord.Interaction
    ) -> None:
        await self._disable_voice_lobby(interaction, use_send=True)

    @staticmethod
    def _format_voice_role_mentions(guild: discord.Guild, role_ids: list[int]) -> str:
        if not role_ids:
            return "Any role"
        mentions: list[str] = []
        for role_id in role_ids:
            role = guild.get_role(role_id)
            mentions.append(role.mention if role else f"Missing({role_id})")
        return ", ".join(mentions)

    async def _show_voice_lobby_status(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return

        from lifeguard.modules.voice_lobby import repo as voice_repo

        config = voice_repo.get_config(self.firestore, interaction.guild.id)
        if config is None:
            await interaction.response.edit_message(
                content=(
                    "Voice lobby is not configured yet.\n"
                    "Use **Entry Channel** and **Defaults** to configure it."
                ),
                embed=None,
                view=VoiceLobbyConfigView(self),
            )
            return

        if config.entry_voice_channel_id is None:
            entry_label = "Not set"
        else:
            entry_channel = interaction.guild.get_channel(config.entry_voice_channel_id)
            if isinstance(entry_channel, discord.VoiceChannel):
                entry_label = entry_channel.mention
            else:
                entry_label = f"Missing({config.entry_voice_channel_id})"

        if config.lobby_category_id is None:
            category_label = "Same category as entry channel"
        else:
            category = interaction.guild.get_channel(config.lobby_category_id)
            if isinstance(category, discord.CategoryChannel):
                category_label = category.mention
            else:
                category_label = f"Missing({config.lobby_category_id})"

        await interaction.response.edit_message(
            content=(
                f"Enabled: **{'Yes' if config.enabled else 'No'}**\n"
                f"Entry channel: {entry_label}\n"
                f"Lobby category: {category_label}\n"
                f"Default user limit: **{config.default_user_limit}**\n"
                f"Name template: `{config.name_template}`\n"
                f"Create roles: {self._format_voice_role_mentions(interaction.guild, config.creator_role_ids)}\n"
                f"Join roles: {self._format_voice_role_mentions(interaction.guild, config.join_role_ids)}"
            ),
            embed=None,
            view=VoiceLobbyConfigView(self),
        )

    async def _set_voice_lobby_entry_channel(
        self,
        interaction: discord.Interaction,
        entry_channel: discord.VoiceChannel,
    ) -> None:
        if not interaction.guild:
            return

        from lifeguard.modules.voice_lobby import repo as voice_repo

        config = voice_repo.get_or_create_config(self.firestore, interaction.guild.id)
        config.enabled = True
        config.entry_voice_channel_id = entry_channel.id
        voice_repo.save_config(self.firestore, config)

        await interaction.response.edit_message(
            content=f"✅ Entry voice channel set to {entry_channel.mention}.",
            embed=None,
            view=VoiceLobbyConfigView(self),
        )

    async def _set_voice_lobby_category(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel | None,
    ) -> None:
        if not interaction.guild:
            return

        from lifeguard.modules.voice_lobby import repo as voice_repo

        config = voice_repo.get_or_create_config(self.firestore, interaction.guild.id)
        config.enabled = True
        config.lobby_category_id = category.id if category else None
        voice_repo.save_config(self.firestore, config)

        if category is None:
            content = "✅ Lobby category reset to **entry channel category**."
        else:
            content = f"✅ Lobby category set to {category.mention}."

        await interaction.response.edit_message(
            content=content,
            embed=None,
            view=VoiceLobbyConfigView(self),
        )

    async def _set_voice_lobby_defaults(
        self,
        interaction: discord.Interaction,
        name_template: str,
        default_user_limit: str,
    ) -> None:
        if not interaction.guild:
            return

        from lifeguard.modules.voice_lobby import repo as voice_repo

        try:
            parsed_user_limit = int(default_user_limit)
        except (TypeError, ValueError):
            await interaction.response.send_message(
                "Default user limit must be a number between 0 and 99.",
                ephemeral=True,
            )
            return

        if parsed_user_limit < 0 or parsed_user_limit > 99:
            await interaction.response.send_message(
                "Default user limit must be a number between 0 and 99.",
                ephemeral=True,
            )
            return

        config = voice_repo.get_or_create_config(self.firestore, interaction.guild.id)
        config.enabled = True
        config.name_template = name_template.strip() or "Lobby - {owner}"
        config.default_user_limit = parsed_user_limit
        voice_repo.save_config(self.firestore, config)

        await interaction.response.send_message(
            (
                "✅ Voice lobby defaults saved.\n"
                f"Template: `{config.name_template}`\n"
                f"Default user limit: **{config.default_user_limit}**"
            ),
            ephemeral=True,
        )

    async def _add_voice_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        *,
        field_name: str,
        label: str,
        return_view: discord.ui.View,
    ) -> None:
        if not interaction.guild:
            return

        from lifeguard.modules.voice_lobby import repo as voice_repo

        config = voice_repo.get_or_create_config(self.firestore, interaction.guild.id)
        role_ids = getattr(config, field_name)
        if role.id in role_ids:
            await interaction.response.edit_message(
                content=f"{role.mention} is already in {label} roles.",
                embed=None,
                view=return_view,
            )
            return

        role_ids.append(role.id)
        setattr(config, field_name, role_ids)
        voice_repo.save_config(self.firestore, config)

        await interaction.response.edit_message(
            content=f"✅ Added {role.mention} to {label} roles.",
            embed=None,
            view=return_view,
        )

    async def _remove_voice_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        *,
        field_name: str,
        label: str,
        return_view: discord.ui.View,
    ) -> None:
        if not interaction.guild:
            return

        from lifeguard.modules.voice_lobby import repo as voice_repo

        config = voice_repo.get_or_create_config(self.firestore, interaction.guild.id)
        role_ids = getattr(config, field_name)
        if role.id not in role_ids:
            await interaction.response.edit_message(
                content=f"{role.mention} is not in {label} roles.",
                embed=None,
                view=return_view,
            )
            return

        role_ids.remove(role.id)
        setattr(config, field_name, role_ids)
        voice_repo.save_config(self.firestore, config)

        await interaction.response.edit_message(
            content=f"✅ Removed {role.mention} from {label} roles.",
            embed=None,
            view=return_view,
        )

    async def _clear_voice_roles(
        self,
        interaction: discord.Interaction,
        *,
        field_name: str,
        label: str,
        return_view: discord.ui.View,
    ) -> None:
        if not interaction.guild:
            return

        from lifeguard.modules.voice_lobby import repo as voice_repo

        config = voice_repo.get_or_create_config(self.firestore, interaction.guild.id)
        setattr(config, field_name, [])
        voice_repo.save_config(self.firestore, config)

        await interaction.response.edit_message(
            content=f"✅ Cleared {label} role restrictions.",
            embed=None,
            view=return_view,
        )

    async def _add_voice_lobby_creator_role(
        self, interaction: discord.Interaction, role: discord.Role
    ) -> None:
        await self._add_voice_role(
            interaction,
            role,
            field_name="creator_role_ids",
            label="creator",
            return_view=VoiceLobbyConfigView(self),
        )

    async def _remove_voice_lobby_creator_role(
        self, interaction: discord.Interaction, role: discord.Role
    ) -> None:
        await self._remove_voice_role(
            interaction,
            role,
            field_name="creator_role_ids",
            label="creator",
            return_view=VoiceLobbyConfigView(self),
        )

    async def _clear_voice_lobby_creator_roles(
        self, interaction: discord.Interaction
    ) -> None:
        await self._clear_voice_roles(
            interaction,
            field_name="creator_role_ids",
            label="creator",
            return_view=VoiceLobbyConfigView(self),
        )

    async def _add_voice_lobby_join_role(
        self, interaction: discord.Interaction, role: discord.Role
    ) -> None:
        await self._add_voice_role(
            interaction,
            role,
            field_name="join_role_ids",
            label="join",
            return_view=VoiceLobbyConfigView(self),
        )

    async def _remove_voice_lobby_join_role(
        self, interaction: discord.Interaction, role: discord.Role
    ) -> None:
        await self._remove_voice_role(
            interaction,
            role,
            field_name="join_role_ids",
            label="join",
            return_view=VoiceLobbyConfigView(self),
        )

    async def _clear_voice_lobby_join_roles(
        self, interaction: discord.Interaction
    ) -> None:
        await self._clear_voice_roles(
            interaction,
            field_name="join_role_ids",
            label="join",
            return_view=VoiceLobbyConfigView(self),
        )

    # ------------------------------------------------------------------
    # Albion enable/disable
    # ------------------------------------------------------------------

    async def _enable_albion_feature(
        self,
        interaction: discord.Interaction,
        feature: str,
        *,
        use_send: bool = False,
    ) -> None:
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
        LOGGER.info("Albion %s enabled: guild=%s", feature, interaction.guild.id)

    async def _disable_albion_feature(
        self, interaction: discord.Interaction, feature: str
    ) -> None:
        """Disable an Albion feature (from config menu — uses edit_message)."""
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
        LOGGER.info("Albion %s disabled: guild=%s", feature, interaction.guild.id)

    async def _disable_albion_feature_direct(
        self, interaction: discord.Interaction, feature: str
    ) -> None:
        """Disable an Albion feature (direct command — uses send_message)."""
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
                    f"{_FEATURE_ALBION_PRICES} is not currently enabled.",
                    ephemeral=True,
                )
                return
            features.albion_prices_enabled = False
            feature_name = _FEATURE_ALBION_PRICES
        else:
            if not features.albion_builds_enabled:
                await interaction.response.send_message(
                    f"{_FEATURE_ALBION_BUILDS} is not currently enabled.",
                    ephemeral=True,
                )
                return
            features.albion_builds_enabled = False
            feature_name = _FEATURE_ALBION_BUILDS

        albion_repo.save_guild_features(self.firestore, features)

        await interaction.response.send_message(
            f"✅ **{feature_name} disabled!**", ephemeral=True
        )
        LOGGER.info("Albion %s disabled: guild=%s", feature, interaction.guild.id)

    async def _show_albion_status(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return

        features = albion_repo.get_guild_features(self.firestore, interaction.guild.id)

        prices_status = (
            _STATUS_ENABLED
            if features and features.albion_prices_enabled
            else _STATUS_DISABLED
        )
        builds_status = (
            _STATUS_ENABLED
            if features and features.albion_builds_enabled
            else _STATUS_DISABLED
        )

        embed = discord.Embed(
            title="⚔️ Albion Features Status",
            color=discord.Color.blue(),
        )
        embed.add_field(name="💰 Price Lookup", value=prices_status, inline=True)
        embed.add_field(name="⚔️ Builds", value=builds_status, inline=True)

        await interaction.response.edit_message(
            embed=embed, view=BackToAlbionView(self)
        )

    # ------------------------------------------------------------------
    # Bot Admin Role helpers
    # ------------------------------------------------------------------

    async def _show_bot_admin_roles(self, interaction: discord.Interaction) -> None:
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

        await interaction.response.edit_message(
            embed=embed, view=BackToGeneralView(self)
        )

    async def _add_bot_admin_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        *,
        use_send: bool = False,
    ) -> None:
        if not interaction.guild:
            return

        features = albion_repo.get_or_create_guild_features(
            self.firestore, interaction.guild.id
        )

        if role.id in features.bot_admin_role_ids:
            await self._respond(
                interaction,
                f"{role.mention} is already a bot admin role.",
                use_send=use_send,
            )
            return

        features.bot_admin_role_ids.append(role.id)
        albion_repo.save_guild_features(self.firestore, features)

        await self._respond(
            interaction,
            f"✅ Added {role.mention} as a bot admin role.",
            use_send=use_send,
        )
        LOGGER.info("Added bot admin role %s: guild=%s", role.id, interaction.guild.id)

    async def _show_remove_bot_admin_role_view(
        self, interaction: discord.Interaction
    ) -> None:
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
            content="Select a role to remove from bot admin roles:",
            embed=None,
            view=view,
        )

    async def _remove_bot_admin_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        *,
        use_send: bool = False,
    ) -> None:
        if not interaction.guild:
            return

        features = albion_repo.get_guild_features(self.firestore, interaction.guild.id)
        if not features or role.id not in features.bot_admin_role_ids:
            await self._respond(
                interaction,
                f"{role.mention} is not a bot admin role.",
                use_send=use_send,
            )
            return

        features.bot_admin_role_ids.remove(role.id)
        albion_repo.save_guild_features(self.firestore, features)

        await self._respond(
            interaction,
            f"✅ Removed {role.mention} from bot admin roles.",
            use_send=use_send,
        )
        LOGGER.info(
            "Removed bot admin role %s: guild=%s", role.id, interaction.guild.id
        )

    async def _clear_bot_admin_roles(self, interaction: discord.Interaction) -> None:
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
            view=BackToGeneralView(self),
        )
        LOGGER.info("Cleared bot admin roles: guild=%s", interaction.guild.id)

    # ------------------------------------------------------------------
    # Content Review enable/disable (delegated)
    # ------------------------------------------------------------------

    async def _disable_content_review_direct(
        self, interaction: discord.Interaction
    ) -> None:
        """Disable content review via /disable-feature command."""
        cr_cog = self.bot.get_cog("ContentReviewCog")
        if not cr_cog:
            await interaction.response.send_message(
                "Content Review module is not loaded.", ephemeral=True
            )
            return
        await cr_cog._disable_content_review_feature(interaction, use_send=True)


async def setup(bot: commands.Bot) -> None:
    """Setup function for loading as an extension."""
    await bot.add_cog(ConfigCog(bot))
