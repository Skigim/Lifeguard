"""Process abstraction: the unit the loader starts, stops and gates per guild."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum


class ProcessState(Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    FAILED = "failed"


class Process(ABC):
    """A self-contained feature with an explicit lifecycle.

    Subclasses set a unique `name`. The loader calls `start` when the first guild
    enables the process and `stop` when the last guild disables it.
    """

    name: str

    @abstractmethod
    async def start(self) -> None:
        """Acquire resources (tasks, clients, caches)."""

    @abstractmethod
    async def stop(self) -> None:
        """Release everything acquired in `start`. Must be safe to call once after start."""

    async def on_guild_enabled(self, guild_id: int) -> None:  # noqa: B027
        """Optional hook: a guild enabled this process while it is running."""

    async def on_guild_disabled(self, guild_id: int) -> None:  # noqa: B027
        """Optional hook: a guild disabled this process."""
