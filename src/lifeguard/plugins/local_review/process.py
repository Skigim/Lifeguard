"""Local HTTP handoff for agents that review Discord discussions."""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import Mapping
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import TYPE_CHECKING

from aiohttp import web

from lifeguard.config import ConfigError
from lifeguard.core.process import Process

if TYPE_CHECKING:
    from lifeguard.bot import LifeguardBot

POLL_TIMEOUT = 20
REVIEW_TIMEOUT = 120
MAX_ISSUES = 3
MAX_TITLE = 256
MAX_BODY = 1200


class ReviewError(RuntimeError):
    """A review failure that can be reported in the source thread."""


@dataclass(frozen=True)
class HookSettings:
    token: str
    host: str = "127.0.0.1"
    port: int = 8090

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> HookSettings:
        token = environ.get("LOCAL_REVIEW_TOKEN", "").strip()
        if not token:
            raise ConfigError("local-review requires LOCAL_REVIEW_TOKEN")
        try:
            port = int(environ.get("LOCAL_REVIEW_PORT", str(cls.port)))
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError as exc:
            raise ConfigError("LOCAL_REVIEW_PORT must be between 1 and 65535") from exc
        return cls(token, environ.get("LOCAL_REVIEW_HOST", "").strip() or cls.host, port)


def parse_issues(data: object) -> list[tuple[str, str]]:
    if not isinstance(data, dict) or set(data) != {"issues"}:
        raise ValueError("Expected an issues object")
    issues = data["issues"]
    if not isinstance(issues, list) or len(issues) > MAX_ISSUES:
        raise ValueError("Invalid issue count")
    result = []
    titles = set()
    for issue in issues:
        if not isinstance(issue, dict) or set(issue) != {"title", "body"}:
            raise ValueError("Invalid issue fields")
        title, body = issue["title"], issue["body"]
        if not isinstance(title, str) or not isinstance(body, str):
            raise ValueError("Issue fields must be text")
        title, body = title.strip(), body.strip()
        if not 0 < len(title) <= MAX_TITLE or not 0 < len(body) <= MAX_BODY:
            raise ValueError("Invalid issue field lengths")
        if title.casefold() not in titles:
            result.append((title, body))
            titles.add(title.casefold())
    return result


@dataclass
class ReviewJob:
    id: str
    guild_id: int
    repo: str
    thread_title: str
    messages: list[str]
    context_limited: bool
    result: asyncio.Future[list[tuple[str, str]]]
    claimed: bool = False


class LocalReview(Process):
    name = "local-review"

    def __init__(self, bot: LifeguardBot) -> None:
        self.bot = bot
        self.available = asyncio.Event()
        self.pending: ReviewJob | None = None
        self.stopping = False

    async def start(self) -> None:
        self.settings = HookSettings.from_env(self.bot.settings.environ)
        expected = f"Bearer {self.settings.token}".encode()

        @web.middleware
        async def require_token(request, handler):
            supplied = request.headers.get("Authorization", "").encode("utf-8", "surrogateescape")
            if not secrets.compare_digest(expected, supplied):
                raise web.HTTPUnauthorized(headers={"WWW-Authenticate": "Bearer"})
            return await handler(request)

        app = web.Application(middlewares=[require_token], client_max_size=64 * 1024)
        app.router.add_get("/v1/health", self.health)
        app.router.add_post("/v1/jobs/next", self.next_job)
        app.router.add_post("/v1/jobs/{job_id}/result", self.submit_result)
        async with AsyncExitStack() as resources:
            self.github = await resources.enter_async_context(self.bot.github_service.connect())
            await self.github.store.execute(
                "CREATE TABLE IF NOT EXISTS local_review_repos "
                "(guild_id INTEGER PRIMARY KEY, repo TEXT NOT NULL)"
            )
            self.runner = web.AppRunner(app, access_log=None, handler_cancellation=True)
            await self.runner.setup()
            resources.push_async_callback(self.runner.cleanup)
            await web.TCPSite(self.runner, self.settings.host, self.settings.port).start()
            self._resources = resources.pop_all()

    async def stop(self) -> None:
        self.stopping = True
        self.available.set()
        if self.pending is not None and not self.pending.result.done():
            self.pending.result.set_exception(ReviewError("Local review was disabled."))
        await self._resources.aclose()

    async def on_guild_disabled(self, guild_id: int) -> None:
        job = self.pending
        if job is not None and job.guild_id == guild_id and not job.result.done():
            job.result.set_exception(ReviewError("Local review was disabled in this server."))

    async def review(
        self,
        guild_id: int,
        repo: str,
        thread_title: str,
        messages: list[str],
        context_limited: bool,
    ) -> list[tuple[str, str]]:
        if self.stopping or self.pending is not None:
            raise ReviewError("The local review hook is unavailable. Try again shortly.")
        result = asyncio.get_running_loop().create_future()
        self.pending = ReviewJob(
            secrets.token_urlsafe(18),
            guild_id,
            repo,
            thread_title,
            messages,
            context_limited,
            result,
        )
        self.available.set()
        try:
            async with asyncio.timeout(REVIEW_TIMEOUT):
                return await result
        except TimeoutError as exc:
            raise ReviewError("No agent completed the review before it expired.") from exc
        finally:
            self.pending = None
            self.available.clear()

    async def health(self, _request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"}, headers={"Cache-Control": "no-store"})

    async def next_job(self, request: web.Request) -> web.Response:
        try:
            async with asyncio.timeout(POLL_TIMEOUT):
                while not self.stopping:
                    await self.available.wait()
                    if self.stopping:
                        break
                    job = self.pending
                    if job is None or job.claimed or job.result.done():
                        self.available.clear()
                        continue
                    job.claimed = True
                    self.available.clear()
                    return web.json_response(
                        {
                            "id": job.id,
                            "action": "review_thread_for_github_issues",
                            "repo": job.repo,
                            "thread": {"title": job.thread_title, "messages": job.messages},
                            "context_limited": job.context_limited,
                        },
                        headers={"Cache-Control": "no-store"},
                    )
        except TimeoutError:
            return web.Response(status=204)
        raise web.HTTPServiceUnavailable(text="Local review is stopping")

    async def submit_result(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            failed = isinstance(data, dict) and set(data) == {"error"} and data["error"] is True
            issues = [] if failed else parse_issues(data)
        except ValueError as exc:
            raise web.HTTPUnprocessableEntity(text=str(exc)) from exc

        job = self.pending
        if job is None or job.id != request.match_info["job_id"] or job.result.done():
            raise web.HTTPNotFound(text="No active job with that ID")
        if not job.claimed:
            raise web.HTTPConflict(text="Claim the job before submitting a result")
        if failed:
            job.result.set_exception(
                ReviewError("The connected agent could not review the thread.")
            )
        else:
            job.result.set_result(issues)
        return web.Response(status=204)
