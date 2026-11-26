import asyncio
import time
from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from lifeguard.config import ConfigError, Settings
from lifeguard.core.github.service import GitHubService
from lifeguard.features.github.process import GitHubBridge
from lifeguard.features.github.recovery import recover


@pytest.mark.parametrize("has_cursor", [False, True])
async def test_recovery_redelivers_unprocessed_and_sweeps(store, payload, has_cursor):
    if has_cursor:
        await store.finish("processed", time.time())
    await store.put("repo_links", guild_id=1, repo="example/demo", forum_id=10, installation_id=12)

    async def deliveries(*args, **kwargs):
        for i, guid in enumerate(["processed", "failed", "accepted-but-lost"]):
            yield {
                "id": i,
                "guid": guid,
                "status_code": 500 if guid == "failed" else 202,
                "delivered_at": "2026-11-14T00:00:00Z",
            }

    seen = []

    async def items(repo, installation, since=None):
        seen.append(since)
        yield payload["issue"]

    api = SimpleNamespace(getiter=deliveries, post=AsyncMock())
    sink = SimpleNamespace(upsert_post=AsyncMock())
    bridge = SimpleNamespace(
        store=store,
        gh=SimpleNamespace(api=api, jwt=lambda: "jwt", list_open=items),
        sink=sink,
        enabled=lambda g: True,
        locks=defaultdict(asyncio.Lock),
    )
    await recover(bridge)
    assert api.post.await_count == (2 if has_cursor else 3)
    if has_cursor:
        sink.upsert_post.assert_awaited_once()
        assert seen[0].endswith("Z")
    else:
        sink.upsert_post.assert_not_awaited()
        assert not seen


async def test_worker_only_marks_success_and_deduplicates(store):
    bot = SimpleNamespace(settings=Settings(env="test", token="x"), wait_until_ready=AsyncMock())
    bridge = GitHubBridge(bot)
    bridge.store = store
    bridge.events = SimpleNamespace(handle=AsyncMock(side_effect=[RuntimeError("failed"), None]))
    task = asyncio.create_task(bridge.work())
    try:
        await bridge.queue.put(("first", time.time(), "issues", {}))
        await bridge.queue.join()
        assert await store.processed("first") is None
        await bridge.queue.put(("first", time.time(), "issues", {}))
        await bridge.queue.join()
        assert await store.processed("first")
        await bridge.queue.put(("first", time.time(), "issues", {}))
        await bridge.queue.join()
        assert bridge.events.handle.await_count == 2
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_missing_settings_fail_before_opening_resources():
    bridge = GitHubBridge(SimpleNamespace(settings=Settings(env="test", token="x")))
    with pytest.raises(ConfigError):
        await bridge.start()


async def test_process_start_stop_releases_resources(tmp_path, unused_tcp_port):
    import aiohttp
    from cryptography.fernet import Fernet

    from lifeguard.config import GitHubSettings

    github = GitHubSettings(
        app_id="1",
        private_key="unused",
        webhook_secret="secret",
        client_id="client",
        client_secret="secret",
        public_url="https://example.com",
        token_key=Fernet.generate_key().decode(),
        web_host="127.0.0.1",
        web_port=unused_tcp_port,
    )
    ready = asyncio.Event()
    bot = SimpleNamespace(
        settings=Settings(
            env="test", token="x", github=github, database_path=str(tmp_path / "bridge.db")
        ),
        wait_until_ready=ready.wait,
    )
    bot.github_service = GitHubService(bot.settings)
    bridge = GitHubBridge(bot)
    await bridge.start()
    try:
        async with (
            aiohttp.ClientSession() as client,
            client.get(f"http://127.0.0.1:{unused_tcp_port}/healthz") as response,
        ):
            assert response.status == 200
        async with bot.github_service.connect() as shared:
            assert shared.gh is bridge.gh
            await bridge.stop()
            assert shared.webhook is None
            assert not shared.session.closed
    finally:
        await bridge.stop()
    assert bridge.session.closed and bridge.worker.done() and bridge.recovery.done()
    with pytest.raises(ValueError, match="no active connection"):
        await bridge.store.one("SELECT 1")
