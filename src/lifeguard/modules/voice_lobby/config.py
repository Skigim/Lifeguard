from __future__ import annotations

from dataclasses import asdict, dataclass, field

from lifeguard.utils import drop_none


@dataclass
class VoiceLobbyConfig:
    """Guild-level configuration for temporary voice lobbies."""

    guild_id: int
    enabled: bool = False
    entry_voice_channel_id: int | None = None
    lobby_category_id: int | None = None
    name_template: str = "Lobby - {owner}"
    default_user_limit: int = 0
    creator_role_ids: list[int] = field(default_factory=list)
    join_role_ids: list[int] = field(default_factory=list)

    def to_firestore(self) -> dict:
        return drop_none(asdict(self))

    @classmethod
    def from_firestore(cls, data: dict) -> VoiceLobbyConfig:
        return cls(
            guild_id=data["guild_id"],
            enabled=data.get("enabled", False),
            entry_voice_channel_id=data.get("entry_voice_channel_id"),
            lobby_category_id=data.get("lobby_category_id"),
            name_template=data.get("name_template", "Lobby - {owner}"),
            default_user_limit=data.get("default_user_limit", 0),
            creator_role_ids=data.get("creator_role_ids") or [],
            join_role_ids=data.get("join_role_ids") or [],
        )
