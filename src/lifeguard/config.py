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
class GitHubSettings:
    app_id: str
    private_key: str
    webhook_secret: str
    client_id: str
    client_secret: str
    public_url: str
    token_key: str
    web_host: str = "0.0.0.0"
    web_port: int = 8080


@dataclass(frozen=True)
class Settings:
    env: str
    token: str
    guild_id: int | None = None
    database_path: str | None = None
    github: GitHubSettings | None = None

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

    github = None
    if env_map.get("GITHUB_APP_ID"):

        def required(key: str) -> str:
            value = env_map.get(key, "").strip()
            if not value:
                raise ConfigError(f"{key} is not set")
            return value

        key = env_map.get("GITHUB_APP_PRIVATE_KEY", "").replace("\\n", "\n")
        if not key and env_map.get("GITHUB_APP_PRIVATE_KEY_PATH"):
            try:
                key = Path(env_map["GITHUB_APP_PRIVATE_KEY_PATH"]).read_text()
            except OSError as exc:
                raise ConfigError("Cannot read GITHUB_APP_PRIVATE_KEY_PATH") from exc
        if not key:
            raise ConfigError("GITHUB_APP_PRIVATE_KEY or GITHUB_APP_PRIVATE_KEY_PATH is required")
        try:
            port = int(env_map.get("WEB_PORT", "8080"))
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError as exc:
            raise ConfigError("WEB_PORT must be between 1 and 65535") from exc
        public_url = required("PUBLIC_URL").rstrip("/")
        if not public_url.startswith("https://"):
            raise ConfigError("PUBLIC_URL must use HTTPS")
        github = GitHubSettings(
            app_id=required("GITHUB_APP_ID"),
            private_key=key,
            webhook_secret=required("GITHUB_WEBHOOK_SECRET"),
            client_id=required("GITHUB_CLIENT_ID"),
            client_secret=required("GITHUB_CLIENT_SECRET"),
            public_url=public_url,
            token_key=required("TOKEN_ENCRYPTION_KEY"),
            web_host=env_map.get("WEB_HOST", "0.0.0.0"),
            web_port=port,
        )
    return Settings(
        env=env,
        token=token,
        guild_id=guild_id,
        database_path=env_map.get("DATABASE_PATH") or None,
        github=github,
    )


def load_settings_from_dotenv(root: Path | None = None) -> Settings:
    """Load `.env.<BOT_ENV>` (if present), then build Settings from os.environ."""
    root = root or Path.cwd()
    env = os.environ.get("BOT_ENV", "test").strip().lower()
    load_dotenv(root / f".env.{env}", override=False)
    return load_settings()
