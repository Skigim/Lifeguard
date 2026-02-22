from __future__ import annotations

import inspect
import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from lifeguard import __version__
from lifeguard.config import Config

if TYPE_CHECKING:
    import aiohttp

LOGGER = logging.getLogger(__name__)


def _get_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _get_git_commit_short() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_get_repo_root(),
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _is_git_dirty() -> bool | None:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=_get_repo_root(),
            capture_output=True,
            text=True,
            check=True,
        )
        return bool(result.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return None


def _iter_command_paths(
    command: app_commands.Command | app_commands.Group,
) -> list[str]:
    """Return executable command paths for a command or command group."""
    if isinstance(command, app_commands.Group):
        paths: list[str] = []
        for child in command.commands:
            paths.extend(_iter_command_paths(child))
        if paths:
            return paths
        return [command.qualified_name]
    return [command.qualified_name]


def _get_registered_command_paths(bot: commands.Bot) -> list[str]:
    """Collect all executable app command paths registered on the command tree."""
    paths: list[str] = []
    for command in bot.tree.get_commands():
        paths.extend(_iter_command_paths(command))
    return sorted(paths)


async def _sync_commands(bot: commands.Bot, config: Config) -> None:
    """Sync app commands, avoiding global+guild duplicates in target guild mode."""
    target_guild_id = config.active_guild_id

    if target_guild_id is not None:
        guild = discord.Object(id=target_guild_id)
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        LOGGER.info("Synced %d app commands to guild %s", len(synced), target_guild_id)

        bot.tree.clear_commands(guild=None)
        cleared = await bot.tree.sync()
        LOGGER.info("Cleared global app commands (remaining: %d)", len(cleared))
    else:
        synced = await bot.tree.sync()
        LOGGER.info("Synced %d global app commands", len(synced))

    command_paths = _get_registered_command_paths(bot)
    LOGGER.info(
        "Registered app command paths (%d): %s",
        len(command_paths),
        ", ".join(command_paths),
    )


def create_bot(config: Config) -> commands.Bot:
    intents = discord.Intents.default()
    intents.message_content = True
    intents.voice_states = True

    bot = commands.Bot(command_prefix=config.command_prefix, intents=intents)
    bot._commands_synced = False  # type: ignore[attr-defined]

    @bot.event
    async def on_ready() -> None:
        env_label = "TEST" if config.is_test else "PRODUCTION"
        git_commit = _get_git_commit_short()
        git_dirty = _is_git_dirty()
        dirty_label = (
            "unknown" if git_dirty is None else ("dirty" if git_dirty else "clean")
        )

        LOGGER.info(
            "[%s] Logged in as %s (%s)",
            env_label,
            bot.user,
            bot.user.id if bot.user else "?",
        )
        LOGGER.info(
            "[%s] Build fingerprint: version=%s git=%s workspace=%s",
            env_label,
            __version__,
            git_commit,
            dirty_label,
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
