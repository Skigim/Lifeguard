"""Configuration Cog – owns /config, /enable-feature, /disable-feature.

This cog is the single owner of all cross-cutting configuration commands and
their supporting helpers.  Module-specific sub-menus delegate back to the
owning module's cog when needed (e.g. Content Review setup).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

import discord
from discord import app_commands
from discord.ext import commands

from lifeguard.cogs.config_views import (
    BackToGeneralView,
    ConfigFeatureSelectView,
    ContentReviewDisabledView,
    GeneralConfigView,
    RemoveBotAdminRoleView,
    TimeImpersonatorConfigView,
    VoiceLobbyConfigView,
)
from lifeguard.guild_settings import (
    get_guild_settings,
    get_or_create_guild_settings,
    save_guild_settings,
)

if TYPE_CHECKING:
    from lifeguard.feature_interfaces import (
        SupportsConfigToggle,
        SupportsContentReviewConfig,
        SupportsVoiceLobbyConfig,
    )
    from google.cloud.firestore import Client as FirestoreClient

LOGGER = logging.getLogger(__name__)

# --- Common Response Strings ---
_MSG_SERVER_ONLY = "Server only."
_MSG_NO_PERMISSION = "You don't have permission to manage bot settings."
_MSG_CONTENT_REVIEW_NOT_LOADED = "Content Review module is not loaded."
_MSG_TIME_IMPERSONATOR_NOT_LOADED = "Time Impersonator module is not loaded."
_MSG_VOICE_LOBBY_NOT_LOADED = "Voice Lobby module is not loaded."
_STATUS_ENABLED = "✅ Enabled"
_STATUS_DISABLED = "❌ Disabled"
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

    def _get_time_impersonator_cog(self) -> "SupportsConfigToggle | None":
        return cast(
            "SupportsConfigToggle | None", self.bot.get_cog("TimeImpersonatorCog")
        )

    def _get_content_review_cog(self) -> "SupportsContentReviewConfig | None":
        return cast(
            "SupportsContentReviewConfig | None", self.bot.get_cog("ContentReviewCog")
        )

    def _get_voice_lobby_cog(self) -> "SupportsVoiceLobbyConfig | None":
        return cast(
            "SupportsVoiceLobbyConfig | None", self.bot.get_cog("VoiceLobbyCog")
        )

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

        settings = get_guild_settings(self.firestore, interaction.guild.id)
        if not settings or not settings.bot_admin_role_ids:
            return False

        user_role_ids = {role.id for role in interaction.user.roles}
        return bool(user_role_ids & set(settings.bot_admin_role_ids))

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
            cr_cog = self._get_content_review_cog()
            if not cr_cog:
                await interaction.response.send_message(
                    _MSG_CONTENT_REVIEW_NOT_LOADED, ephemeral=True
                )
                return
            await cr_cog.show_setup(interaction, use_send=True)
            return

        # Simple features enable directly
        if feature == "time_impersonator":
            await self._enable_time_impersonator(interaction, use_send=True)
        elif feature == "voice_lobby":
            await self._enable_voice_lobby(interaction, use_send=True)

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
        cr_cog = self._get_content_review_cog()
        if cr_cog is None:
            await interaction.response.edit_message(
                content=_MSG_CONTENT_REVIEW_NOT_LOADED,
                embed=None,
                view=None,
            )
            return

        await cr_cog.show_config_menu(
            interaction,
            disabled_view=ContentReviewDisabledView(self),
            on_back_to_home=self._show_config_home,
        )

    async def _show_content_review_setup(
        self, interaction: discord.Interaction
    ) -> None:
        """Show the Content Review setup flow from the disabled config view."""
        cr_cog = self._get_content_review_cog()
        if cr_cog is None:
            await interaction.response.edit_message(
                content=_MSG_CONTENT_REVIEW_NOT_LOADED,
                embed=None,
                view=None,
            )
            return

        await cr_cog.show_setup(interaction)

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
        cog = self._get_time_impersonator_cog()
        if cog is None:
            await interaction.response.edit_message(
                content=_MSG_TIME_IMPERSONATOR_NOT_LOADED,
                embed=None,
                view=None,
            )
            return
        await cog.show_config_status(
            interaction,
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
        cog = self._get_time_impersonator_cog()
        if cog is None:
            await interaction.response.send_message(
                _MSG_TIME_IMPERSONATOR_NOT_LOADED,
                ephemeral=True,
            )
            return
        await cog.enable_feature(interaction, use_send=use_send)

    async def _disable_time_impersonator(
        self,
        interaction: discord.Interaction,
        *,
        use_send: bool = False,
    ) -> None:
        cog = self._get_time_impersonator_cog()
        if cog is None:
            await interaction.response.send_message(
                _MSG_TIME_IMPERSONATOR_NOT_LOADED,
                ephemeral=True,
            )
            return
        await cog.disable_feature(interaction, use_send=use_send)

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
        cog = self._get_voice_lobby_cog()
        if cog is None:
            await interaction.response.send_message(
                _MSG_VOICE_LOBBY_NOT_LOADED,
                ephemeral=True,
            )
            return
        await cog.enable_feature(interaction, use_send=use_send)

    async def _disable_voice_lobby(
        self,
        interaction: discord.Interaction,
        *,
        use_send: bool = False,
    ) -> None:
        cog = self._get_voice_lobby_cog()
        if cog is None:
            await interaction.response.send_message(
                _MSG_VOICE_LOBBY_NOT_LOADED,
                ephemeral=True,
            )
            return
        await cog.disable_feature(interaction, use_send=use_send)

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
        cog = self._get_voice_lobby_cog()
        if cog is None:
            await interaction.response.edit_message(
                content=_MSG_VOICE_LOBBY_NOT_LOADED,
                embed=None,
                view=None,
            )
            return
        await cog.show_config_status(interaction, view=VoiceLobbyConfigView(self))

    async def _set_voice_lobby_entry_channel(
        self,
        interaction: discord.Interaction,
        entry_channel: discord.VoiceChannel,
    ) -> None:
        cog = self._get_voice_lobby_cog()
        if cog is None:
            await interaction.response.send_message(
                _MSG_VOICE_LOBBY_NOT_LOADED,
                ephemeral=True,
            )
            return
        await cog.set_entry_channel(
            interaction,
            entry_channel,
            view=VoiceLobbyConfigView(self),
        )

    async def _set_voice_lobby_category(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel | None,
    ) -> None:
        cog = self._get_voice_lobby_cog()
        if cog is None:
            await interaction.response.send_message(
                _MSG_VOICE_LOBBY_NOT_LOADED,
                ephemeral=True,
            )
            return
        await cog.set_category(
            interaction,
            category,
            view=VoiceLobbyConfigView(self),
        )

    async def _set_voice_lobby_defaults(
        self,
        interaction: discord.Interaction,
        name_template: str,
        default_user_limit: str,
    ) -> None:
        cog = self._get_voice_lobby_cog()
        if cog is None:
            await interaction.response.send_message(
                _MSG_VOICE_LOBBY_NOT_LOADED,
                ephemeral=True,
            )
            return
        await cog.set_defaults(interaction, name_template, default_user_limit)

    async def _add_voice_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        *,
        field_name: str,
        label: str,
        return_view: discord.ui.View,
    ) -> None:
        cog = self._get_voice_lobby_cog()
        if cog is None:
            await interaction.response.send_message(
                _MSG_VOICE_LOBBY_NOT_LOADED,
                ephemeral=True,
            )
            return

        if field_name == "creator_role_ids":
            await cog.add_creator_role(interaction, role, view=return_view)
            return

        await cog.add_join_role(interaction, role, view=return_view)

    async def _remove_voice_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        *,
        field_name: str,
        label: str,
        return_view: discord.ui.View,
    ) -> None:
        cog = self._get_voice_lobby_cog()
        if cog is None:
            await interaction.response.send_message(
                _MSG_VOICE_LOBBY_NOT_LOADED,
                ephemeral=True,
            )
            return

        if field_name == "creator_role_ids":
            await cog.remove_creator_role(interaction, role, view=return_view)
            return

        await cog.remove_join_role(interaction, role, view=return_view)

    async def _clear_voice_roles(
        self,
        interaction: discord.Interaction,
        *,
        field_name: str,
        label: str,
        return_view: discord.ui.View,
    ) -> None:
        cog = self._get_voice_lobby_cog()
        if cog is None:
            await interaction.response.send_message(
                _MSG_VOICE_LOBBY_NOT_LOADED,
                ephemeral=True,
            )
            return

        if field_name == "creator_role_ids":
            await cog.clear_creator_roles(interaction, view=return_view)
            return

        await cog.clear_join_roles(interaction, view=return_view)

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
    # Bot Admin Role helpers
    # ------------------------------------------------------------------

    async def _show_bot_admin_roles(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return

        settings = get_guild_settings(self.firestore, interaction.guild.id)
        role_ids = settings.bot_admin_role_ids if settings else []

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

        settings = get_or_create_guild_settings(self.firestore, interaction.guild.id)

        if role.id in settings.bot_admin_role_ids:
            await self._respond(
                interaction,
                f"{role.mention} is already a bot admin role.",
                use_send=use_send,
            )
            return

        settings.bot_admin_role_ids.append(role.id)
        save_guild_settings(self.firestore, settings)

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

        settings = get_guild_settings(self.firestore, interaction.guild.id)
        if not settings or not settings.bot_admin_role_ids:
            await interaction.response.edit_message(
                content="No bot admin roles configured.", embed=None, view=None
            )
            return

        view = RemoveBotAdminRoleView(self, settings.bot_admin_role_ids)
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

        settings = get_guild_settings(self.firestore, interaction.guild.id)
        if not settings or role.id not in settings.bot_admin_role_ids:
            await self._respond(
                interaction,
                f"{role.mention} is not a bot admin role.",
                use_send=use_send,
            )
            return

        settings.bot_admin_role_ids.remove(role.id)
        save_guild_settings(self.firestore, settings)

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

        settings = get_guild_settings(self.firestore, interaction.guild.id)
        if not settings or not settings.bot_admin_role_ids:
            await interaction.response.edit_message(
                content="No bot admin roles to clear.", embed=None, view=None
            )
            return

        settings.bot_admin_role_ids = []
        save_guild_settings(self.firestore, settings)

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
        cr_cog = self._get_content_review_cog()
        if not cr_cog:
            await interaction.response.send_message(
                _MSG_CONTENT_REVIEW_NOT_LOADED, ephemeral=True
            )
            return
        await cr_cog.disable_feature(interaction, use_send=True)


async def setup(bot: commands.Bot) -> None:
    """Setup function for loading as an extension."""
    await bot.add_cog(ConfigCog(bot))
