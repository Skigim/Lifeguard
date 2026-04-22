from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from google.cloud.firestore import Client as FirestoreClient


GUILD_SETTINGS_COLLECTION = "guild_settings"


@dataclass
class GuildSettings:
    """Cross-cutting guild settings that are not owned by any feature module."""

    guild_id: int
    bot_admin_role_ids: list[int] = field(default_factory=list)

    def to_firestore(self) -> dict:
        return {
            "guild_id": self.guild_id,
            "bot_admin_role_ids": self.bot_admin_role_ids,
        }

    @classmethod
    def from_firestore(cls, data: dict) -> GuildSettings:
        return cls(
            guild_id=data["guild_id"],
            bot_admin_role_ids=data.get("bot_admin_role_ids", []),
        )


def get_guild_settings(
    firestore: FirestoreClient, guild_id: int
) -> GuildSettings | None:
    """Fetch guild settings for a guild if they exist."""
    doc = firestore.collection(GUILD_SETTINGS_COLLECTION).document(str(guild_id)).get()
    if not doc.exists:
        return None
    return GuildSettings.from_firestore(doc.to_dict())


def get_or_create_guild_settings(
    firestore: FirestoreClient, guild_id: int
) -> GuildSettings:
    """Fetch guild settings, returning a default instance when missing."""
    settings = get_guild_settings(firestore, guild_id)
    if settings is None:
        settings = GuildSettings(guild_id=guild_id)
    return settings


def save_guild_settings(firestore: FirestoreClient, settings: GuildSettings) -> None:
    """Persist guild settings."""
    firestore.collection(GUILD_SETTINGS_COLLECTION).document(str(settings.guild_id)).set(
        settings.to_firestore(), merge=True
    )
