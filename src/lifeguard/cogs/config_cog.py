"""Configuration Cog – owns /config, /enable-feature, /disable-feature."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from lifeguard.cogs.config_views import (
    BackToGeneralView,
    ConfigHomeView,
    ConfigUnavailableFeatureView,
    GeneralConfigView,
    RemoveBotAdminRoleView,
)
from lifeguard.features.availability import FeatureEntry, resolve_feature_entries
from lifeguard.features.registry import FeatureRegistry
from lifeguard.guild_settings import (
    get_guild_settings,
    get_or_create_guild_settings,
    remember_feature_key,
    save_guild_settings,
)

if TYPE_CHECKING:
    from google.cloud.firestore import Client as FirestoreClient

LOGGER = logging.getLogger(__name__)


def build_feature_autocomplete_choices(
    feature_entries: list[FeatureEntry],
    current: str,
) -> list[app_commands.Choice[str]]:
    current_lower = current.lower()
    matches: list[app_commands.Choice[str]] = []
    for entry in feature_entries:
        if entry.status != "available":
            continue
        haystacks = (entry.feature_key.lower(), entry.display_name.lower())
        if current_lower and not any(current_lower in haystack for haystack in haystacks):
            continue
        matches.append(
            app_commands.Choice(
                name=f"{entry.display_name} - {entry.description}",
                value=entry.feature_key,
            )
        )
    return matches[:25]


_MSG_SERVER_ONLY = "Server only."
_MSG_NO_PERMISSION = "You don't have permission to manage bot settings."


async def feature_autocomplete(  # NOSONAR - discord.py requires async
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    if not interaction.guild:
        return []

    registry = getattr(interaction.client, "lifeguard_features", None)
    firestore = getattr(interaction.client, "lifeguard_firestore", None)
    if registry is None or firestore is None:
        return []

    settings = get_or_create_guild_settings(firestore, interaction.guild.id)
    entries = resolve_feature_entries(registry, settings)
    return build_feature_autocomplete_choices(entries, current)


class ConfigCog(commands.Cog):
    """Central configuration commands and cross-cutting config helpers."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @property
    def firestore(self) -> FirestoreClient:
        return self.bot.lifeguard_firestore  # type: ignore[attr-defined]

    @property
    def feature_registry(self) -> FeatureRegistry:
        return self.bot.lifeguard_features  # type: ignore[attr-defined]

    def _feature_entries(self, guild_id: int) -> list[FeatureEntry]:
        self._backfill_known_feature_keys(guild_id)
        settings = get_or_create_guild_settings(self.firestore, guild_id)
        return resolve_feature_entries(self.feature_registry, settings)

    def _remember_feature(self, guild_id: int, feature_key: str) -> None:
        settings = get_or_create_guild_settings(self.firestore, guild_id)
        remember_feature_key(settings, feature_key)
        save_guild_settings(self.firestore, settings)

    def _backfill_known_feature_keys(self, guild_id: int) -> None:
        settings = get_or_create_guild_settings(self.firestore, guild_id)
        changed = False
        for manifest in self.feature_registry.all_manifests():
            document = self.firestore.collection(
                f"{manifest.feature_key}_configs"
            ).document(str(guild_id)).get()
            if not document.exists:
                continue
            before = list(settings.known_feature_keys)
            remember_feature_key(settings, manifest.feature_key)
            if settings.known_feature_keys != before:
                changed = True
        if changed:
            save_guild_settings(self.firestore, settings)

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

    async def _dispatch_feature_menu(
        self,
        interaction: discord.Interaction,
        feature_key: str,
    ) -> None:
        manifest = self.feature_registry.get_manifest(feature_key)
        adapter = self.feature_registry.build_adapter(self.bot, feature_key)
        if manifest is None or adapter is None:
            await interaction.response.edit_message(
                content=f"{feature_key.replace('_', ' ').title()} is not currently installed.",
                embed=None,
                view=ConfigUnavailableFeatureView(self),
            )
            return

        if interaction.guild is not None:
            self._remember_feature(interaction.guild.id, feature_key)

        await adapter.show_menu(interaction, on_back_to_home=self._show_config_home)

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

        manifest = self.feature_registry.get_manifest(feature)
        adapter = self.feature_registry.build_adapter(self.bot, feature)
        if manifest is None or adapter is None:
            await interaction.response.send_message(
                f"Unknown feature: `{feature}`. Use autocomplete to select a valid feature.",
                ephemeral=True,
            )
            return

        self._remember_feature(interaction.guild.id, feature)

        if manifest.requires_setup:
            await adapter.show_setup(
                interaction,
                on_back_to_home=self._show_config_home,
                use_send=True,
            )
            return

        await adapter.enable(
            interaction,
            on_back_to_home=self._show_config_home,
            use_send=True,
        )

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

        manifest = self.feature_registry.get_manifest(feature)
        adapter = self.feature_registry.build_adapter(self.bot, feature)
        if manifest is None or adapter is None:
            await interaction.response.send_message(
                f"Unknown feature: `{feature}`. Use autocomplete to select a valid feature.",
                ephemeral=True,
            )
            return

        self._remember_feature(interaction.guild.id, feature)
        await adapter.disable(interaction, use_send=True)

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

    async def _show_config_home(
        self, interaction: discord.Interaction, *, use_send: bool = False
    ) -> None:
        feature_entries = (
            self._feature_entries(interaction.guild.id) if interaction.guild else []
        )
        if use_send:
            await interaction.response.send_message(
                embed=self._build_config_home_embed(),
                view=ConfigHomeView(self, feature_entries=feature_entries),
                ephemeral=True,
            )
            return
        await interaction.response.edit_message(
            embed=self._build_config_home_embed(),
            view=ConfigHomeView(self, feature_entries=feature_entries),
            content=None,
        )

    async def _show_general_menu(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=self._build_general_embed(),
            view=GeneralConfigView(self),
            content=None,
        )

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

async def setup(bot: commands.Bot) -> None:
    """Setup function for loading as an extension."""
    await bot.add_cog(ConfigCog(bot))
