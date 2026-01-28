from __future__ import annotations

from typing import TYPE_CHECKING

from lifeguard.modules.time_impersonator.config import TimeImpersonatorConfig
from lifeguard.modules.time_impersonator.models import UserTimezone

if TYPE_CHECKING:
    from google.cloud.firestore import Client as FirestoreClient


# Collection names
CONFIGS_COLLECTION = "time_impersonator_configs"
USER_TIMEZONES_COLLECTION = "user_timezones"


def _guild_doc_id(guild_id: int) -> str:
    """Generate document ID for guild-level documents."""
    return str(guild_id)


def _user_doc_id(user_id: int) -> str:
    """Generate document ID for user timezone documents."""
    return str(user_id)


# --- Config CRUD ---


def get_config(firestore: FirestoreClient, guild_id: int) -> TimeImpersonatorConfig | None:
    """Get the time impersonator configuration for a guild."""
    doc = firestore.collection(CONFIGS_COLLECTION).document(_guild_doc_id(guild_id)).get()
    if not doc.exists:
        return None
    return TimeImpersonatorConfig.from_firestore(doc.to_dict())


def save_config(firestore: FirestoreClient, config: TimeImpersonatorConfig) -> None:
    """Save or update a guild's time impersonator configuration."""
    firestore.collection(CONFIGS_COLLECTION).document(
        _guild_doc_id(config.guild_id)
    ).set(config.to_firestore(), merge=True)


# --- User Timezone CRUD ---


def get_user_timezone(firestore: FirestoreClient, user_id: int) -> UserTimezone | None:
    """Get a user's saved timezone."""
    doc = (
        firestore.collection(USER_TIMEZONES_COLLECTION)
        .document(_user_doc_id(user_id))
        .get()
    )
    if not doc.exists:
        return None
    return UserTimezone.from_firestore(doc.to_dict())


def save_user_timezone(firestore: FirestoreClient, user_tz: UserTimezone) -> None:
    """Save or update a user's timezone."""
    firestore.collection(USER_TIMEZONES_COLLECTION).document(
        _user_doc_id(user_tz.user_id)
    ).set(user_tz.to_firestore(), merge=True)


def delete_user_timezone(firestore: FirestoreClient, user_id: int) -> None:
    """Delete a user's saved timezone."""
    firestore.collection(USER_TIMEZONES_COLLECTION).document(
        _user_doc_id(user_id)
    ).delete()
