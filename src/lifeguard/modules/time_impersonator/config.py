from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TimeImpersonatorConfig:
    """Guild-level configuration for the Time Impersonator module."""

    guild_id: int
    enabled: bool = False

    def to_firestore(self) -> dict:
        return {
            "guild_id": self.guild_id,
            "enabled": self.enabled,
        }

    @classmethod
    def from_firestore(cls, data: dict) -> TimeImpersonatorConfig:
        return cls(
            guild_id=data["guild_id"],
            enabled=data.get("enabled", False),
        )
