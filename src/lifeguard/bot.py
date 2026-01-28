from __future__ import annotations

import logging

import discord
from discord.ext import commands

from lifeguard.config import Config


LOGGER = logging.getLogger(__name__)


def create_bot(config: Config) -> commands.Bot:
    intents = discord.Intents.default()
    intents.message_content = True

    bot = commands.Bot(command_prefix=config.command_prefix, intents=intents)
    bot._commands_synced = False  # type: ignore[attr-defined]

    @bot.event
    async def on_ready() -> None:
        LOGGER.info("Logged in as %s (%s)", bot.user, bot.user.id if bot.user else "?")

        # Only sync commands once, not on every reconnect
        if bot._commands_synced:  # type: ignore[attr-defined]
            return

        try:
            if config.guild_id is not None:
                guild = discord.Object(id=config.guild_id)
                
                # Sync to guild
                bot.tree.copy_global_to(guild=guild)
                synced = await bot.tree.sync(guild=guild)
                LOGGER.info("Synced %d app commands to guild %s", len(synced), config.guild_id)
                
                # Clear global commands to prevent duplicates (sync empty global)
                bot.tree.clear_commands(guild=None)
                await bot.tree.sync()
                LOGGER.info("Cleared global commands")
            else:
                synced = await bot.tree.sync()
                LOGGER.info("Synced %d global app commands", len(synced))
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
        # Albion cog disabled for now
        # await bot.add_cog(_load_albion_cog(bot, config, session))
        await bot.add_cog(_load_content_review_cog(bot))
        await bot.add_cog(_load_time_impersonator_cog(bot))

    @bot.event
    async def close() -> None:
        session = getattr(bot, "lifeguard_http_session", None)
        if session is not None:
            await session.close()

        firestore_client = getattr(bot, "lifeguard_firestore", None)
        if firestore_client is not None:
            close = getattr(firestore_client, "close", None)
            if callable(close):
                close()

    return bot


def _load_core_cog(bot: commands.Bot) -> commands.Cog:
    from lifeguard.cogs.core import CoreCog

    return CoreCog(bot)


def _load_albion_cog(
    bot: commands.Bot,
    config: Config,
    session: "aiohttp.ClientSession",
) -> commands.Cog:
    from lifeguard.modules.albion.cog import AlbionCog

    return AlbionCog(bot, config, session)


def _load_content_review_cog(bot: commands.Bot) -> commands.Cog:
    from lifeguard.modules.content_review.cog import ContentReviewCog

    return ContentReviewCog(bot)


def _load_time_impersonator_cog(bot: commands.Bot) -> commands.Cog:
    from lifeguard.modules.time_impersonator.cog import TimeImpersonatorCog

    return TimeImpersonatorCog(bot)
