"""One shared web listener and event worker, gated by per-guild enablement."""

import asyncio
import logging
from collections import defaultdict
from contextlib import AsyncExitStack

import aiohttp
from aiohttp import web

from lifeguard.config import ConfigError
from lifeguard.core.process import Process

from .events import Events
from .gh import GitHub
from .recovery import recover
from .store import Store
from .sync import DiscordSink
from .web import make_app

log = logging.getLogger(__name__)


class GitHubBridge(Process):
    name = "github"

    def __init__(self, bot):
        self.bot = bot
        self.settings = bot.settings.github
        self.queue = asyncio.Queue(maxsize=10000)
        self.locks = defaultdict(asyncio.Lock)
        self.resources = AsyncExitStack()

    def enabled(self, guild_id):
        return self.bot.loader.is_enabled(self.name, guild_id)

    async def start(self):
        if not self.settings or not self.bot.settings.database_path:
            raise ConfigError("github requires GitHub App settings and DATABASE_PATH")
        try:
            self.store = await Store.open(self.bot.settings.database_path)
            self.resources.push_async_callback(self.store.close)
            self.session = await self.resources.enter_async_context(
                aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
            )
            self.gh = GitHub(self.session, self.settings, self.store)
            self.sink = DiscordSink(self.bot, self.store)
            self.events = Events(self.store, self.gh, self.sink, self.enabled, self.locks)
            self.runner = web.AppRunner(make_app(self), access_log=None)
            await self.runner.setup()
            self.resources.push_async_callback(self.runner.cleanup)
            await web.TCPSite(self.runner, self.settings.web_host, self.settings.web_port).start()
            self.worker = asyncio.create_task(self.work(), name="github-events")
            self.recovery = asyncio.create_task(self.recover_ready(), name="github-recovery")
            self.resources.push_async_callback(self.cancel_tasks)
        except BaseException:
            await self.resources.aclose()
            raise

    async def cancel_tasks(self):
        for task in (self.worker, self.recovery):
            task.cancel()
        await asyncio.gather(self.worker, self.recovery, return_exceptions=True)

    async def stop(self):
        await self.resources.aclose()

    async def recover_ready(self):
        await self.bot.wait_until_ready()
        try:
            await recover(self)
        except Exception:  # noqa: BLE001 - background boundary; keep worker alive
            log.exception("GitHub recovery failed")

    async def work(self):
        await self.bot.wait_until_ready()
        while True:
            delivery, received, event, payload = await self.queue.get()
            try:
                if not await self.store.processed(delivery):
                    await self.events.handle(event, payload)
                    await self.store.finish(delivery, received)
            except Exception:  # noqa: BLE001 - never mark a failed delivery processed
                log.exception("GitHub delivery %s failed; eligible for redelivery", delivery)
            finally:
                self.queue.task_done()

    async def backfill(self, link):
        count = 0
        async for item in self.gh.list_open(link["repo"], link["installation_id"]):
            async with self.locks[(link["repo"], item["number"])]:
                await self.sink.upsert_post(link, item)
                count += 1
        return count
