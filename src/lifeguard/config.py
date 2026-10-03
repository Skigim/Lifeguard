"""Environment-driven configuration. Defaults to test mode."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

VALID_ENVS = ("test", "production")


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    env: str
    token: str
    guild_id: int | None = None

    @property
    def is_production(self) -> bool:
        return self.env == "production"


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    """Build Settings from a mapping (defaults to os.environ)."""
    env_map = os.environ if environ is None else environ

    env = env_map.get("BOT_ENV", "test").strip().lower()
    if env not in VALID_ENVS:
        raise ConfigError(f"BOT_ENV must be one of {VALID_ENVS}, got {env!r}")

    token = env_map.get("DISCORD_TOKEN", "").strip()
    if not token:
        raise ConfigError("DISCORD_TOKEN is not set")

    raw_guild = env_map.get("GUILD_ID", "").strip()
    try:
        guild_id = int(raw_guild) if raw_guild else None
    except ValueError as exc:
        raise ConfigError(f"GUILD_ID must be an integer, got {raw_guild!r}") from exc

    return Settings(env=env, token=token, guild_id=guild_id)


def load_settings_from_dotenv(root: Path | None = None) -> Settings:
    """Load `.env.<BOT_ENV>` (if present), then build Settings from os.environ."""
    root = root or Path.cwd()
    env = os.environ.get("BOT_ENV", "test").strip().lower()
    load_dotenv(root / f".env.{env}", override=False)
    return load_settings()
