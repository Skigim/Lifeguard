"""Loader: the single owner of process lifecycles and per-guild enablement."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Protocol

from lifeguard.core.process import Process, ProcessState

log = logging.getLogger(__name__)


class UnknownProcess(KeyError):
    pass


class ProcessDisabled(RuntimeError):
    pass


class EnablementStore(Protocol):
    """Persistence boundary for which guild has which process enabled."""

    def guilds_for(self, name: str) -> set[int]: ...
    def add(self, name: str, guild_id: int) -> None: ...
    def remove(self, name: str, guild_id: int) -> None: ...


class InMemoryEnablementStore:
    def __init__(self) -> None:
        self._data: dict[str, set[int]] = {}

    def guilds_for(self, name: str) -> set[int]:
        return set(self._data.get(name, ()))

    def add(self, name: str, guild_id: int) -> None:
        self._data.setdefault(name, set()).add(guild_id)

    def remove(self, name: str, guild_id: int) -> None:
        self._data.get(name, set()).discard(guild_id)


class Loader:
    def __init__(self, store: EnablementStore | None = None) -> None:
        self._store: EnablementStore = store or InMemoryEnablementStore()
        self._factories: dict[str, Callable[[], Process]] = {}
        self._running: dict[str, Process] = {}
        self._state: dict[str, ProcessState] = {}
        self._lock = asyncio.Lock()

    def register(self, name: str, factory: Callable[[], Process]) -> None:
        if name in self._factories:
            raise ValueError(f"process {name!r} already registered")
        self._factories[name] = factory
        self._state[name] = ProcessState.STOPPED

    @property
    def names(self) -> list[str]:
        return sorted(self._factories)

    def state(self, name: str) -> ProcessState:
        self._check(name)
        return self._state[name]

    def is_enabled(self, name: str, guild_id: int) -> bool:
        self._check(name)
        return guild_id in self._store.guilds_for(name)

    async def enable(self, name: str, guild_id: int) -> None:
        self._check(name)
        async with self._lock:
            self._store.add(name, guild_id)
            proc = self._running.get(name)
            if proc is None:
                await self._start(name)
            else:
                await proc.on_guild_enabled(guild_id)

    async def disable(self, name: str, guild_id: int) -> None:
        self._check(name)
        async with self._lock:
            self._store.remove(name, guild_id)
            proc = self._running.get(name)
            if proc is None:
                return
            await proc.on_guild_disabled(guild_id)
            if not self._store.guilds_for(name):
                await self._stop(name)

    def require(self, name: str, guild_id: int) -> Process:
        """Return the running process for a guild, or raise ProcessDisabled."""
        self._check(name)
        proc = self._running.get(name)
        if proc is None or guild_id not in self._store.guilds_for(name):
            raise ProcessDisabled(f"{name!r} is not enabled for guild {guild_id}")
        return proc

    async def start_enabled(self) -> None:
        """On boot: start every registered process that any guild has enabled."""
        async with self._lock:
            for name in self.names:
                if self._store.guilds_for(name) and name not in self._running:
                    await self._start(name)

    async def shutdown(self) -> None:
        async with self._lock:
            for name in list(self._running):
                await self._stop(name)

    def _check(self, name: str) -> None:
        if name not in self._factories:
            raise UnknownProcess(name)

    async def _start(self, name: str) -> None:
        proc = self._factories[name]()
        try:
            await proc.start()
        except Exception:
            self._state[name] = ProcessState.FAILED
            log.exception("process %s failed to start", name)
            raise
        self._running[name] = proc
        self._state[name] = ProcessState.RUNNING
        log.info("process %s started", name)

    async def _stop(self, name: str) -> None:
        proc = self._running.pop(name)
        try:
            await proc.stop()
        except Exception:
            self._state[name] = ProcessState.FAILED
            log.exception("process %s failed to stop cleanly", name)
        else:
            self._state[name] = ProcessState.STOPPED
            log.info("process %s stopped", name)
