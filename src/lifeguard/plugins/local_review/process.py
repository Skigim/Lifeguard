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
from lifeguard.core.github.store import Store
from lifeguard.core.process import Process

if TYPE_CHECKING:
    from lifeguard.bot import LifeguardBot
    from lifeguard.core.github.service import GitHubService

POLL_TIMEOUT = 20
REVIEW_TIMEOUT = 120
MAX_ISSUES = 3
MAX_TITLE = 256
MAX_BODY = 1200
MAX_REPLY = 1900
ISSUE_ACTION = "review_thread_for_github_issues"
REPLY_ACTION = "respond_to_prompt"
REFERENCE_ACTION = "respond_to_reference"


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


def parse_reply(data: object) -> str:
    if not isinstance(data, dict) or set(data) != {"reply"} or not isinstance(data["reply"], str):
        raise ValueError("Expected a reply string")
    reply = data["reply"].strip()
    if not 0 < len(reply.encode("utf-16-le")) // 2 <= MAX_REPLY:
        raise ValueError(f"Reply must contain 1 to {MAX_REPLY} characters")
    return reply


@dataclass(frozen=True)
class Followup:
    action: str
    text: str
    repo: str | None
    pr_number: int | None
    issues: list[tuple[str, str]]


ReviewResult = str | list[tuple[str, str]] | Followup
PLAYFUL_REACTIONS = {"🤨", "🙄", "😔", "😂", "👀"}


def parse_followup(data: object) -> Followup:
    fields = {"action", "text", "repo", "pr_number", "issues"}
    if not isinstance(data, dict) or set(data) != fields:
        raise ValueError("Invalid reference result fields")
    action, text, repo, number = data["action"], data["text"], data["repo"], data["pr_number"]
    if action not in ("ignore", "reply", "react", "create_issues", "post_pr_comment"):
        raise ValueError("Unsupported reference action")
    if not isinstance(text, str) or (repo is not None and not isinstance(repo, str)):
        raise ValueError("Invalid reference result text or repository")
    if number is not None and (type(number) is not int or number <= 0):
        raise ValueError("Invalid pull request number")
    issues = parse_issues({"issues": data["issues"]})
    text = text.strip()
    if action == "reply":
        text = parse_reply({"reply": text})
    if action == "react" and text not in PLAYFUL_REACTIONS:
        raise ValueError("Unsupported reaction emoji")
    if action == "post_pr_comment" and not 0 < len(text) <= 4000:
        raise ValueError("Invalid pull request comment length")
    return Followup(action, text, repo, number, issues)


@dataclass
class ReviewJob:
    id: str
    guild_id: int
    repo: str | None
    prompt: str
    thread_title: str | None
    messages: list[str]
    context_limited: bool
    result: asyncio.Future[ReviewResult]
    reference: dict[str, str | bool | None] | None
    claimed: bool = False

    @property
    def action(self) -> str:
        if self.reference is not None:
            return REFERENCE_ACTION
        return ISSUE_ACTION if self.repo is not None else REPLY_ACTION


class LocalReview(Process):
    name = "local-review"

    def __init__(self, bot: LifeguardBot) -> None:
        self.bot = bot
        self.github: GitHubService | None = None
        self.mention_roles: dict[int, int] = {}
        self.config_store: Store | None = None
        self.available = asyncio.Condition()
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
            if self.bot.settings.database_path:
                self.config_store = await Store.open(self.bot.settings.database_path)
                resources.push_async_callback(self.config_store.close)
                await self.config_store.execute(
                    "CREATE TABLE IF NOT EXISTS local_review_mention_roles "
                    "(guild_id INTEGER PRIMARY KEY, role_id INTEGER NOT NULL)"
                )
                rows = await self.config_store.all(
                    "SELECT guild_id, role_id FROM local_review_mention_roles"
                )
                self.mention_roles = {row["guild_id"]: row["role_id"] for row in rows}
            if self.bot.settings.github and self.bot.settings.database_path:
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

    async def set_mention_role(self, guild_id: int, role_id: int) -> None:
        if self.config_store is not None:
            await self.config_store.put(
                "local_review_mention_roles", guild_id=guild_id, role_id=role_id
            )
        self.mention_roles[guild_id] = role_id

    async def stop(self) -> None:
        async with self.available:
            self.stopping = True
            self.available.notify_all()
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
        prompt: str,
        thread_title: str | None,
        messages: list[str],
        context_limited: bool,
        *,
        repo: str | None = None,
        reference: dict[str, str | bool | None] | None = None,
    ) -> ReviewResult:
        async with self.available:
            if self.stopping or self.pending is not None:
                raise ReviewError("The local review hook is unavailable. Try again shortly.")
            result = asyncio.get_running_loop().create_future()
            self.pending = ReviewJob(
                secrets.token_urlsafe(18),
                guild_id,
                repo,
                prompt,
                thread_title,
                messages,
                context_limited,
                result,
                reference,
            )
            self.available.notify_all()
        try:
            async with asyncio.timeout(REVIEW_TIMEOUT):
                return await result
        except TimeoutError as exc:
            raise ReviewError("No agent completed the review before it expired.") from exc
        finally:
            self.pending = None

    async def health(self, _request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"}, headers={"Cache-Control": "no-store"})

    async def next_job(self, request: web.Request) -> web.Response:
        include_replies = request.query.get("include_replies") == "true"
        actions = {ISSUE_ACTION}
        if include_replies:
            actions.add(REPLY_ACTION)
        if request.query.get("include_references") == "true":
            actions.add(REFERENCE_ACTION)

        def ready() -> bool:
            job = self.pending
            return self.stopping or (
                job is not None
                and not job.claimed
                and not job.result.done()
                and job.action in actions
            )

        try:
            async with asyncio.timeout(POLL_TIMEOUT), self.available:
                await self.available.wait_for(ready)
                if self.stopping:
                    raise web.HTTPServiceUnavailable(text="Local review is stopping")
                job = self.pending
                assert job is not None
                job.claimed = True
                thread = None
                if job.thread_title is not None:
                    thread = {"title": job.thread_title, "messages": job.messages}
                payload = {
                    "id": job.id,
                    "action": job.action,
                    "thread": thread,
                    "context_limited": job.context_limited,
                }
                if include_replies or job.reference is not None:
                    payload["prompt"] = job.prompt
                if job.reference is not None:
                    payload["reference"] = job.reference
                if job.repo is not None:
                    payload["repo"] = job.repo
                return web.json_response(payload, headers={"Cache-Control": "no-store"})
        except TimeoutError:
            return web.Response(status=204)

    async def submit_result(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except ValueError as exc:
            raise web.HTTPUnprocessableEntity(text="Expected a JSON result") from exc

        job = self.pending
        if job is None or job.id != request.match_info["job_id"] or job.result.done():
            raise web.HTTPNotFound(text="No active job with that ID")
        if not job.claimed:
            raise web.HTTPConflict(text="Claim the job before submitting a result")
        if isinstance(data, dict) and set(data) == {"error"} and data["error"] is True:
            job.result.set_exception(
                ReviewError("The connected agent could not complete the request.")
            )
        else:
            try:
                if job.reference is not None:
                    result = parse_followup(data)
                else:
                    result = parse_issues(data) if job.repo is not None else parse_reply(data)
            except ValueError as exc:
                raise web.HTTPUnprocessableEntity(text=str(exc)) from exc
            job.result.set_result(result)
        return web.Response(status=204)
