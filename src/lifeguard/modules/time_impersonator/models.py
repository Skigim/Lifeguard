from __future__ import annotations

from dataclasses import dataclass


@dataclass
class UserTimezone:
    """Stores a user's preferred timezone for time parsing."""

    user_id: int
    timezone: str

    def to_firestore(self) -> dict:
        return {
            "user_id": self.user_id,
            "timezone": self.timezone,
        }

    @classmethod
    def from_firestore(cls, data: dict) -> UserTimezone:
        return cls(
            user_id=data["user_id"],
            timezone=data["timezone"],
        )
