from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LobbyInstance:
    """Represents a created temporary lobby voice channel."""

    guild_id: int
    owner_id: int
    voice_channel_id: int

    def to_firestore(self) -> dict:
        return {
            "guild_id": self.guild_id,
            "owner_id": self.owner_id,
            "voice_channel_id": self.voice_channel_id,
        }

    @classmethod
    def from_firestore(cls, data: dict) -> LobbyInstance:
        return cls(
            guild_id=data["guild_id"],
            owner_id=data["owner_id"],
            voice_channel_id=data["voice_channel_id"],
        )
