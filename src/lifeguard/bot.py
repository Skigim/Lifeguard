from __future__ import annotations

import inspect
import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from lifeguard.config import Config

if TYPE_CHECKING:
    import aiohttp

LOGGER = logging.getLogger(__name__)


async def _sync_commands(bot: commands.Bot, config: Config) -> None:
    """Sync app commands to the target guild or globally."""
    target_guild_id = config.active_guild_id

    if target_guild_id is not None:
        guild = discord.Object(id=target_guild_id)
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        LOGGER.info("Synced %d app commands to guild %s", len(synced), target_guild_id)

        # Clear global commands to prevent duplicates
        bot.tree.clear_commands(guild=None)
        await bot.tree.sync()
        LOGGER.info("Cleared global commands")
    else:
        synced = await bot.tree.sync()
        LOGGER.info("Synced %d global app commands", len(synced))


def create_bot(config: Config) -> commands.Bot:
    intents = discord.Intents.default()
    intents.message_content = True
    intents.voice_states = True

    bot = commands.Bot(command_prefix=config.command_prefix, intents=intents)
    bot._commands_synced = False  # type: ignore[attr-defined]

    @bot.event
    async def on_ready() -> None:
        env_label = "TEST" if config.is_test else "PRODUCTION"
        LOGGER.info(
            "[%s] Logged in as %s (%s)",
            env_label,
            bot.user,
            bot.user.id if bot.user else "?",
        )

        if bot._commands_synced:  # type: ignore[attr-defined]
            return

        try:
            await _sync_commands(bot, config)
            bot._commands_synced = True  # type: ignore[attr-defined]
        except Exception:
            LOGGER.exception("Failed to sync app commands")

    @bot.event
    async def setup_hook() -> None:
        import aiohttp

        from lifeguard.firestore_client import init_firestore

        session = aiohttp.ClientSession(headers={"Accept-Encoding": "gzip"})
        bot.lifeguard_http_session = session  # type: ignore[attr-defined]

        firestore_client = init_firestore(config)
        bot.lifeguard_firestore = firestore_client  # type: ignore[attr-defined]

        await bot.add_cog(_load_core_cog(bot))
        await bot.add_cog(_load_config_cog(bot))
        # Albion cog disabled for now
        # await bot.add_cog(_load_albion_cog(bot, config, session))
        await bot.add_cog(_load_content_review_cog(bot))
        await bot.add_cog(_load_time_impersonator_cog(bot))
        await bot.add_cog(_load_voice_lobby_cog(bot))

    original_close = bot.close

    @bot.event
    async def close() -> None:
        session = getattr(bot, "lifeguard_http_session", None)
        if session is not None:
            await session.close()

        firestore_client = getattr(bot, "lifeguard_firestore", None)
        if firestore_client is not None:
            close_fn = getattr(firestore_client, "close", None)
            if callable(close_fn):
                result = close_fn()
                if inspect.isawaitable(result):
                    await result

        await original_close()

    return bot


def _load_core_cog(bot: commands.Bot) -> commands.Cog:
    from lifeguard.cogs.core import CoreCog

    return CoreCog(bot)


def _load_config_cog(bot: commands.Bot) -> commands.Cog:
    from lifeguard.cogs.config_cog import ConfigCog

    return ConfigCog(bot)


def _load_albion_cog(
    bot: commands.Bot,
    config: Config,
    session: aiohttp.ClientSession,
) -> commands.Cog:
    from lifeguard.modules.albion.cog import AlbionCog

    return AlbionCog(bot, config, session)


def _load_content_review_cog(bot: commands.Bot) -> commands.Cog:
    from lifeguard.modules.content_review.cog import ContentReviewCog

    return ContentReviewCog(bot)


def _load_time_impersonator_cog(bot: commands.Bot) -> commands.Cog:
    from lifeguard.modules.time_impersonator.cog import TimeImpersonatorCog

    return TimeImpersonatorCog(bot)


def _load_voice_lobby_cog(bot: commands.Bot) -> commands.Cog:
    from lifeguard.modules.voice_lobby.cog import VoiceLobbyCog

    return VoiceLobbyCog(bot)
