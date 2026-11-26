"""Bot construction and startup."""

from __future__ import annotations

import asyncio
import logging
from functools import partial

import discord
from discord import app_commands
from discord.ext import commands

from lifeguard.config import Settings
from lifeguard.core.db import SqliteEnablementStore
from lifeguard.core.github.service import GitHubService
from lifeguard.core.loader import Loader, ProcessDisabled, ProcessStartFailed
from lifeguard.core.plugins import discover_plugins
from lifeguard.core.replies import reply
from lifeguard.features import FEATURE_EXTENSIONS, FEATURES

log = logging.getLogger(__name__)

EXTENSIONS = ("lifeguard.cogs.core", "lifeguard.cogs.feature_admin", *FEATURE_EXTENSIONS)

DISABLED_MESSAGE = (
    "That feature isn't enabled on this server. An admin can turn it on with `/feature enable`."
)


async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
) -> None:
    if getattr(interaction, "extras", {}).get("github_error_handled"):
        return
    original = getattr(error, "original", error)
    if isinstance(original, ProcessDisabled):
        message = DISABLED_MESSAGE
    elif isinstance(original, ProcessStartFailed):
        message = str(original)
    else:
        log.error("Unhandled command error", exc_info=error)
        message = "Something went wrong running that command."
    await reply(interaction, message)


class LifeguardBot(commands.Bot):
    def __init__(self, settings: Settings, loader: Loader | None = None) -> None:
        self.plugins = discover_plugins()
        intents = discord.Intents.default()
        for plugin in self.plugins:
            for intent in plugin.intents(settings):
                setattr(intents, intent, True)
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.settings = settings
        self.github_service = GitHubService(settings)
        self._plugin_commands: dict[str, app_commands.Group] = {}
        self._feature_lock = asyncio.Lock()
        self.enablement_store = (
            SqliteEnablementStore(settings.database_path)
            if settings.database_path and loader is None
            else None
        )
        self.loader = loader or Loader(self.enablement_store)
        self.tree.error(on_app_command_error)

    async def load_features(self) -> None:
        """Register processes, start any already-enabled ones, then load their commands."""
        for name, factory in FEATURES.items():
            self.loader.register(name, partial(factory, self))
        for plugin in self.plugins:
            try:
                if plugin.name in self.loader.names:
                    raise ValueError(f"Feature {plugin.name!r} is already registered")
                cog = plugin.cog(self)
                group = cog.guild_commands
                if any(other.name == group.name for other in self._plugin_commands.values()):
                    raise ValueError(f"Command group {group.name!r} is already registered")
                await self.add_cog(cog)
                self.loader.register(plugin.name, partial(plugin.process, self))
                self._plugin_commands[plugin.name] = group
            except Exception:  # noqa: BLE001 - an optional module cannot prevent startup
                log.exception("Skipping optional feature %s", plugin.name)
        await self.loader.start_enabled()
        for ext in EXTENSIONS:
            await self.load_extension(ext)

    async def setup_hook(self) -> None:
        await self.load_features()

        guild_ids = self.loader.command_guilds()
        for name in self._plugin_commands:
            guild_ids.update(self.loader.guilds_for(name))
        if self.settings.guild_id is None:
            synced = await self.tree.sync()
            log.info("Synced %d global app commands", len(synced))
        else:
            guild_ids.add(self.settings.guild_id)
        for guild_id in sorted(guild_ids):
            await self._sync_guild_commands(guild_id)

    async def set_feature_enabled(self, name: str, guild_id: int, enabled: bool) -> bool:
        async with self._feature_lock:
            if enabled:
                await self.loader.enable(name, guild_id)
            else:
                await self.loader.disable(name, guild_id)
            if name in self._plugin_commands:
                return await self._sync_guild_commands(guild_id)
        return True

    async def _sync_guild_commands(self, guild_id: int) -> bool:
        guild = discord.Object(id=guild_id)
        if guild_id == self.settings.guild_id:
            self.tree.copy_global_to(guild=guild)
        enabled = False
        for name, group in self._plugin_commands.items():
            if self.loader.is_enabled(name, guild_id):
                self.tree.add_command(group, guild=guild, override=True)
                enabled = True
            else:
                self.tree.remove_command(group.name, guild=guild)
        self.loader.track_command_guild(guild_id, True)
        try:
            synced = await self.tree.sync(guild=guild)
        except discord.HTTPException:
            log.exception("Couldn't sync app commands for guild %d", guild_id)
            return False
        self.loader.track_command_guild(guild_id, enabled)
        log.info("Synced %d app commands for guild %d", len(synced), guild_id)
        return True

    async def close(self) -> None:
        await self.loader.shutdown()
        if self.enablement_store:
            self.enablement_store.close()
        await super().close()

    async def on_ready(self) -> None:
        log.info("[%s] Logged in as %s", self.settings.env.upper(), self.user)


def run(settings: Settings) -> None:
    configure_logging()
    LifeguardBot(settings).run(settings.token, log_handler=None)


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
