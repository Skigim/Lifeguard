"""Firestore repository for Albion module."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from lifeguard.modules.albion.models import BuildDoc, GuildDoc, PlayerDoc, ZoneDoc

if TYPE_CHECKING:
    from google.cloud.firestore import Client as FirestoreClient


GUILD_FEATURES_COLLECTION = "guild_features"


@dataclass
class GuildFeatures:
    """Per-guild feature flags and settings."""

    guild_id: int
    albion_prices_enabled: bool = False
    albion_builds_enabled: bool = False
    bot_admin_role_ids: list[int] = field(default_factory=list)

    def to_firestore(self) -> dict:
        return {
            "guild_id": self.guild_id,
            "albion_prices_enabled": self.albion_prices_enabled,
            "albion_builds_enabled": self.albion_builds_enabled,
            "bot_admin_role_ids": self.bot_admin_role_ids,
        }

    @classmethod
    def from_firestore(cls, data: dict) -> "GuildFeatures":
        return cls(
            guild_id=data["guild_id"],
            albion_prices_enabled=data.get("albion_prices_enabled", False),
            albion_builds_enabled=data.get("albion_builds_enabled", False),
            bot_admin_role_ids=data.get("bot_admin_role_ids", []),
        )


def get_guild_features(
    firestore: "FirestoreClient", guild_id: int
) -> GuildFeatures | None:
    """Get guild feature flags."""
    doc = firestore.collection(GUILD_FEATURES_COLLECTION).document(str(guild_id)).get()
    if not doc.exists:
        return None
    return GuildFeatures.from_firestore(doc.to_dict())


def get_or_create_guild_features(
    firestore: "FirestoreClient", guild_id: int
) -> GuildFeatures:
    """Get or create guild feature flags."""
    features = get_guild_features(firestore, guild_id)
    if features is None:
        features = GuildFeatures(guild_id=guild_id)
    return features


def save_guild_features(firestore: "FirestoreClient", features: GuildFeatures) -> None:
    """Save guild feature flags."""
    firestore.collection(GUILD_FEATURES_COLLECTION).document(
        str(features.guild_id)
    ).set(features.to_firestore(), merge=True)


_slug_re = re.compile(r"[^a-z0-9_-]+")


def _doc_id(value: str) -> str:
    """Generate a URL-safe document ID from a string."""
    value = value.strip().lower()
    value = value.replace(" ", "-")
    value = _slug_re.sub("", value)
    return value or "unknown"


def upsert_guild(firestore: FirestoreClient, *, name: str) -> None:
    """Create or update a guild document."""
    now = datetime.now(timezone.utc)
    doc = GuildDoc(name=name, updated_at=now)
    firestore.collection("guilds").document(_doc_id(name)).set(
        doc.to_firestore(), merge=True
    )


def upsert_zone(firestore: FirestoreClient, *, name: str) -> None:
    """Create or update a zone document."""
    now = datetime.now(timezone.utc)
    doc = ZoneDoc(name=name, updated_at=now)
    firestore.collection("zones").document(_doc_id(name)).set(
        doc.to_firestore(), merge=True
    )


def upsert_player(
    firestore: FirestoreClient,
    *,
    name: str,
    guild_name: str | None = None,
) -> None:
    """Create or update a player document."""
    now = datetime.now(timezone.utc)
    doc = PlayerDoc(name=name, guild_name=guild_name, updated_at=now)
    firestore.collection("players").document(_doc_id(name)).set(
        doc.to_firestore(), merge=True
    )


def write_build(firestore: FirestoreClient, *, build: BuildDoc) -> str:
    """Write a build document and return the document ID."""
    ref = firestore.collection("builds").document()
    ref.set(build.to_firestore())
    return ref.id


def get_build(firestore: FirestoreClient, build_id: str) -> dict | None:
    """Get a build document by ID."""
    doc = firestore.collection("builds").document(build_id).get()
    if not doc.exists:
        return None
    return doc.to_dict()
