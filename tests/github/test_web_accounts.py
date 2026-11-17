import asyncio
import hashlib
import hmac
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiohttp
import pytest
from aioresponses import aioresponses
from cryptography.fernet import Fernet

from lifeguard.features.github.cogs import BridgeError, author_comment
from lifeguard.features.github.gh import GitHub, RelinkRequired
from lifeguard.features.github.web import make_app


@pytest.fixture
def settings():
    return SimpleNamespace(
        webhook_secret="test-secret",
        token_key=Fernet.generate_key().decode(),
        app_id="1",
        private_key="unused",
        client_id="client",
        client_secret="secret",
        public_url="https://bridge.example",
    )


def signed(body, delivery="delivery-1"):
    return {
        "Content-Type": "application/json",
        "X-GitHub-Event": "issues",
        "X-GitHub-Delivery": delivery,
        "X-Hub-Signature-256": "sha256="
        + hmac.new(b"test-secret", body, hashlib.sha256).hexdigest(),
    }


async def test_webhook_signature_dedupe_and_queue(store, settings, aiohttp_client, payload):
    bridge = SimpleNamespace(settings=settings, store=store, queue=asyncio.Queue())
    client = await aiohttp_client(make_app(bridge))
    body = json.dumps(payload).encode()
    assert (await client.post("/github/webhook", data=body)).status == 401
    assert (
        await client.post("/github/webhook", data=body + b" ", headers=signed(body))
    ).status == 401
    assert (await client.post("/github/webhook", data=body, headers=signed(body))).status == 202
    assert await store.processed("delivery-1") is None
    await store.finish("delivery-1", time.time())
    assert (await client.post("/github/webhook", data=body, headers=signed(body))).status == 200
    assert bridge.queue.qsize() == 1
    assert (await client.get("/healthz")).status == 200


async def test_oauth_single_use_state_and_encrypted_storage(store, settings, aiohttp_client):
    async with aiohttp.ClientSession() as session:
        gh = GitHub(session, settings, store)
        bridge = SimpleNamespace(settings=settings, store=store, gh=gh)
        client = await aiohttp_client(make_app(bridge))
        await store.put("oauth_states", state="valid", discord_id=5, created_at=time.time())
        with aioresponses(passthrough=[str(client.make_url("/"))]) as mock:
            mock.post(
                "https://github.com/login/oauth/access_token",
                payload={
                    "access_token": "access",
                    "refresh_token": "refresh",
                    "expires_in": 28800,
                    "refresh_token_expires_in": 100000,
                },
            )
            mock.get("https://api.github.com/user", payload={"id": 7, "login": "alice"})
            result = await client.get("/oauth/callback?state=valid&code=code")
            assert result.status == 200
            assert (await client.get("/oauth/callback?state=valid&code=code")).status == 400
        row = await store.one("SELECT * FROM user_links WHERE discord_id=5")
        assert row["access_enc"] != "access" and row["refresh_enc"] != "refresh"
        assert await gh.user_token(5) == "access"
        await store.put("oauth_states", state="expired", discord_id=5, created_at=time.time() - 601)
        assert (await client.get("/oauth/callback?state=expired&code=code")).status == 400
        assert (await client.get("/oauth/start?state=unknown")).status == 400


async def test_changed_encryption_key_removes_link(store, settings):
    async with aiohttp.ClientSession() as session:
        gh = GitHub(session, settings, store)
        await gh.save_user(5, {"access_token": "private"}, {"id": 7, "login": "alice"})
        settings.token_key = Fernet.generate_key().decode()
        other = GitHub(session, settings, store)
        with pytest.raises(RelinkRequired):
            await other.user_token(5)
        assert await store.one("SELECT * FROM user_links WHERE discord_id=5") is None


async def test_refresh_and_comment_rest_methods(store, settings):
    async with aiohttp.ClientSession() as session:
        gh = GitHub(session, settings, store)
        await gh.save_user(
            5,
            {
                "access_token": "old",
                "expires_in": -1,
                "refresh_token": "refresh",
                "refresh_token_expires_in": 10000,
            },
            {"id": 7, "login": "alice"},
        )
        row = dict(repo="example/demo", number=42, gh_kind="issue_comment", gh_comment_id=99)
        with aioresponses() as mock:
            mock.post(
                "https://github.com/login/oauth/access_token",
                payload={
                    "access_token": "new",
                    "refresh_token": "new-refresh",
                    "expires_in": 28800,
                    "refresh_token_expires_in": 10000,
                },
            )
            assert await gh.user_token(5) == "new"
            mock.patch(
                "https://api.github.com/repos/example/demo/issues/comments/99",
                payload={"id": 99, "body": "edited"},
            )
            assert (await gh.edit_comment(row, "edited", "new"))["body"] == "edited"
            mock.delete("https://api.github.com/repos/example/demo/issues/comments/99", status=204)
            await gh.delete_comment(row, "new")
        assert await gh.user_token(5) == "new"


@pytest.mark.parametrize(
    "linked,author,allowed", [(True, 7, True), (True, 8, False), (False, 7, False)]
)
async def test_author_check(store, linked, author, allowed):
    await store.put("repo_links", guild_id=1, repo="example/demo", forum_id=10, installation_id=12)
    await store.put(
        "posts",
        guild_id=1,
        repo="example/demo",
        number=42,
        thread_id=20,
        starter_msg_id=20,
        kind="Issue",
        state="Open",
    )
    await store.put(
        "comments",
        guild_id=1,
        repo="example/demo",
        number=42,
        gh_comment_id=99,
        gh_kind="issue_comment",
        gh_author_id=author,
        thread_id=20,
        message_id=30,
        collapsed=0,
    )
    gh = SimpleNamespace(user_token=AsyncMock(return_value="token"))
    if linked:
        await store.put("user_links", discord_id=5, gh_id=7, gh_login="alice")
    else:
        gh.user_token.side_effect = RelinkRequired("Link your account")
    proc = SimpleNamespace(store=store, gh=gh)
    interaction = SimpleNamespace(guild_id=1, channel_id=20, user=SimpleNamespace(id=5))
    if allowed:
        row, token = await author_comment(proc, interaction, 30)
        assert row["gh_author_id"] == 7 and token == "token"
    else:
        with pytest.raises((BridgeError, RelinkRequired)):
            await author_comment(proc, interaction, 30)
