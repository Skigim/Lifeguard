from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

LOGGER = logging.getLogger(__name__)

BotEnv = Literal["production", "test"]


def _parse_int_env(name: str) -> int | None:
    """Parse an optional integer environment variable."""
    raw = os.getenv(name)
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer")


@dataclass(frozen=True)
class Config:
    bot_env: BotEnv
    discord_token: str | None
    guild_id: int | None
    test_guild_id: int | None
    command_prefix: str
    log_level: str
    albion_data_base: str
    albion_gameinfo_base: str
    firebase_enabled: bool
    firebase_credentials_path: str | None
    firebase_project_id: str | None

    @property
    def is_test(self) -> bool:
        """Whether the bot is running in test mode."""
        return self.bot_env == "test"

    @property
    def active_guild_id(self) -> int | None:
        """The guild ID the bot should target for command sync.

        In test mode, returns test_guild_id (falling back to guild_id).
        In production, returns guild_id.
        """
        if self.is_test:
            return self.test_guild_id or self.guild_id
        return self.guild_id


def _load_env_files(bot_env: BotEnv) -> None:
    """Load the appropriate .env files based on bot environment.

    Loading order (later files do NOT override earlier ones):
      test  -> .env.test, .env
      production -> .env
    """
    root = Path.cwd()
    if bot_env == "test":
        test_env = root / ".env.test"
        if test_env.is_file():
            load_dotenv(test_env, override=False)
            LOGGER.info("Loaded environment from %s", test_env)
        else:
            LOGGER.warning(
                "BOT_ENV=test but .env.test not found — falling back to .env"
            )
    # Always try .env as fallback
    load_dotenv(override=False)


def load_config() -> Config:
    # BOT_ENV can be set before dotenv is loaded (e.g. shell var, VS Code task)
    bot_env_raw = os.getenv("BOT_ENV", "production").strip().lower()
    if bot_env_raw not in ("production", "test"):
        raise ValueError("BOT_ENV must be 'production' or 'test'")
    bot_env: BotEnv = bot_env_raw  # type: ignore[assignment]

    _load_env_files(bot_env)

    token = os.getenv("DISCORD_TOKEN")
    guild_id = _parse_int_env("GUILD_ID")
    test_guild_id = _parse_int_env("TEST_GUILD_ID")
    prefix = os.getenv("COMMAND_PREFIX", "!")
    log_level = os.getenv("LOG_LEVEL", "INFO")

    albion_data_base = os.getenv("ALBION_DATA_BASE", "https://west.albion-online-data.com")
    albion_gameinfo_base = os.getenv(
        "ALBION_GAMEINFO_BASE", "https://gameinfo.albiononline.com/api/gameinfo"
    )

    firebase_enabled_raw = os.getenv("FIREBASE_ENABLED", "false").strip().lower()
    firebase_enabled = firebase_enabled_raw in {"1", "true", "yes", "y", "on"}
    firebase_credentials_path = os.getenv("FIREBASE_CREDENTIALS_PATH") or None
    firebase_project_id = os.getenv("FIREBASE_PROJECT_ID") or None

    LOGGER.info("Bot environment: %s", bot_env)
    if bot_env == "test" and test_guild_id:
        LOGGER.info("Test guild ID: %s", test_guild_id)

    return Config(
        bot_env=bot_env,
        discord_token=token,
        guild_id=guild_id,
        test_guild_id=test_guild_id,
        command_prefix=prefix,
        log_level=log_level,
        albion_data_base=albion_data_base,
        albion_gameinfo_base=albion_gameinfo_base,
        firebase_enabled=firebase_enabled,
        firebase_credentials_path=firebase_credentials_path,
        firebase_project_id=firebase_project_id,
    )
