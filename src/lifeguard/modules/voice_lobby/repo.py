from __future__ import annotations

from typing import TYPE_CHECKING

from lifeguard.modules.voice_lobby.config import VoiceLobbyConfig

if TYPE_CHECKING:
    from google.cloud.firestore import Client as FirestoreClient


CONFIGS_COLLECTION = "voice_lobby_configs"


def _guild_doc_id(guild_id: int) -> str:
    return str(guild_id)


def get_config(firestore: FirestoreClient, guild_id: int) -> VoiceLobbyConfig | None:
    """Get voice lobby configuration for a guild."""
    doc = firestore.collection(CONFIGS_COLLECTION).document(_guild_doc_id(guild_id)).get()
    if not doc.exists:
        return None
    return VoiceLobbyConfig.from_firestore(doc.to_dict())


def get_or_create_config(firestore: FirestoreClient, guild_id: int) -> VoiceLobbyConfig:
    """Get existing config or a default in-memory config."""
    config = get_config(firestore, guild_id)
    if config is None:
        config = VoiceLobbyConfig(guild_id=guild_id)
    return config


def save_config(firestore: FirestoreClient, config: VoiceLobbyConfig) -> None:
    """Save voice lobby configuration."""
    firestore.collection(CONFIGS_COLLECTION).document(_guild_doc_id(config.guild_id)).set(
        config.to_firestore(), merge=True
    )
