"""Bot construction and startup."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from lifeguard.config import Settings
from lifeguard.core.loader import Loader, ProcessDisabled
from lifeguard.features import FEATURE_EXTENSIONS, FEATURES

log = logging.getLogger(__name__)

EXTENSIONS = ("lifeguard.cogs.core", "lifeguard.cogs.feature_admin", *FEATURE_EXTENSIONS)

DISABLED_MESSAGE = (
    "That feature isn't enabled on this server. "
    "An admin can turn it on with `/feature enable`."
)


async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
) -> None:
    original = getattr(error, "original", error)
    if isinstance(original, ProcessDisabled):
        message = DISABLED_MESSAGE
    else:
        log.error("Unhandled command error", exc_info=error)
        message = "Something went wrong running that command."
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


class LifeguardBot(commands.Bot):
    def __init__(self, settings: Settings, loader: Loader | None = None) -> None:
        super().__init__(command_prefix=commands.when_mentioned, intents=discord.Intents.default())
        self.settings = settings
        self.loader = loader or Loader()
        self.tree.error(on_app_command_error)

    async def load_features(self) -> None:
        """Register processes, start any already-enabled ones, then load their commands."""
        for name, factory in FEATURES.items():
            self.loader.register(name, factory)
        await self.loader.start_enabled()
        for ext in EXTENSIONS:
            await self.load_extension(ext)

    async def setup_hook(self) -> None:
        await self.load_features()

        if self.settings.guild_id:
            guild = discord.Object(id=self.settings.guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
        else:
            synced = await self.tree.sync()
        log.info("Synced %d app commands", len(synced))

    async def close(self) -> None:
        await self.loader.shutdown()
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
