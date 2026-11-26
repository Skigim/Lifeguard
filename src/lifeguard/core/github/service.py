"""Keep one GitHub client and OAuth listener for the features using them."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack, asynccontextmanager

import aiohttp
from aiohttp import web

from lifeguard.config import ConfigError, Settings

from .client import GitHub
from .store import Store
from .web import make_app


class GitHubService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings.github
        self.path = settings.database_path
        self.webhook: Callable[[web.Request], Awaitable[web.Response]] | None = None
        self._lock = asyncio.Lock()
        self._users = 0
        self._resources = AsyncExitStack()

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[GitHubService]:
        async with self._lock:
            if self._users == 0:
                await self._start()
            self._users += 1
        try:
            yield self
        finally:
            async with self._lock:
                self._users -= 1
                if self._users == 0:
                    await self._resources.aclose()

    async def _start(self) -> None:
        if self.settings is None or self.path is None:
            raise ConfigError("GitHub requires GitHub App settings and DATABASE_PATH")
        async with AsyncExitStack() as resources:
            self.store = await Store.open(self.path)
            resources.push_async_callback(self.store.close)
            self.session = await resources.enter_async_context(
                aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
            )
            self.gh = GitHub(self.session, self.settings, self.store)
            runner = web.AppRunner(make_app(self, self._receive_webhook), access_log=None)
            await runner.setup()
            resources.push_async_callback(runner.cleanup)
            await web.TCPSite(runner, self.settings.web_host, self.settings.web_port).start()
            self._resources = resources.pop_all()

    async def _receive_webhook(self, request: web.Request) -> web.Response:
        handler = self.webhook
        if handler is None:
            raise web.HTTPServiceUnavailable(text="GitHub bridge is disabled")
        return await handler(request)
