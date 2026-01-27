from __future__ import annotations

from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    discord_token: str | None
    guild_id: int | None
    command_prefix: str
    log_level: str
    albion_data_base: str
    albion_gameinfo_base: str
    firebase_enabled: bool
    firebase_credentials_path: str | None
    firebase_project_id: str | None


def load_config() -> Config:
    load_dotenv(override=False)

    import os

    token = os.getenv("DISCORD_TOKEN")
    guild_id_raw = os.getenv("GUILD_ID")
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

    guild_id: int | None
    if guild_id_raw:
        try:
            guild_id = int(guild_id_raw)
        except ValueError:
            raise ValueError("GUILD_ID must be an integer")
    else:
        guild_id = None

    return Config(
        discord_token=token,
        guild_id=guild_id,
        command_prefix=prefix,
        log_level=log_level,
        albion_data_base=albion_data_base,
        albion_gameinfo_base=albion_gameinfo_base,
        firebase_enabled=firebase_enabled,
        firebase_credentials_path=firebase_credentials_path,
        firebase_project_id=firebase_project_id,
    )
