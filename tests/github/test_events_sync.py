import asyncio
from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from lifeguard.features.github.events import Events
from lifeguard.features.github.render import post_embed
from lifeguard.features.github.sync import DiscordSink


@pytest.fixture
async def link(store):
    link = dict(guild_id=1, repo="example/demo", forum_id=10, installation_id=12)
    await store.put("repo_links", **link)
    return link


@pytest.mark.parametrize(
    "action", ["opened", "edited", "labeled", "unlabeled", "closed", "reopened"]
)
async def test_issue_events(store, payload, link, action):
    sink = SimpleNamespace(upsert_post=AsyncMock(), notice=AsyncMock())
    events = Events(store, None, sink, lambda g: True, defaultdict(asyncio.Lock))
    payload["action"] = action
    await events.handle("issues", payload)
    sink.upsert_post.assert_awaited_once()
    assert sink.notice.await_count == int(action in {"closed", "reopened"})


async def test_merge_delete_transfer_and_disabled(store, payload, link):
    sink = SimpleNamespace(upsert_post=AsyncMock(), notice=AsyncMock())
    events = Events(store, None, sink, lambda g: True, defaultdict(asyncio.Lock))
    payload["action"] = "deleted"
    await events.handle("issues", payload)
    sink.notice.assert_awaited_once_with(
        link, payload["issue"], "Deleted on GitHub.", locked=True, archived=True
    )
    sink.upsert_post.assert_not_awaited()
    payload["action"] = "closed"
    payload["pull_request"] = payload.pop("issue")
    payload["pull_request"]["merged"] = True
    await events.handle("pull_request", payload)
    assert "Merged" in sink.notice.call_args.args[2]
    payload["action"] = "transferred"
    await events.handle("issues", payload)
    assert sink.notice.call_args.kwargs["archived"]
    events.enabled = lambda g: False
    sink.upsert_post.reset_mock()
    await events.handle("issues", payload)
    sink.upsert_post.assert_not_awaited()


@pytest.mark.parametrize(
    "event,kind",
    [
        ("issue_comment", "issue_comment"),
        ("pull_request_review", "review"),
        ("pull_request_review_comment", "review_comment"),
    ],
)
async def test_lazy_comment_dispatch(store, payload, link, event, kind):
    sink = SimpleNamespace(upsert_post=AsyncMock(), comment=AsyncMock())
    gh = SimpleNamespace(get_issue=AsyncMock(return_value=payload["issue"]))
    events = Events(store, gh, sink, lambda g: True, defaultdict(asyncio.Lock))
    payload["action"] = "created"
    await events.handle(event, payload)
    gh.get_issue.assert_awaited_once()
    assert sink.comment.call_args.args[-2:] == (kind, "created")


class Thread:
    def __init__(self, id=20):
        self.id, self.archived, self.locked = id, True, False
        self.edits = []
        self.message = SimpleNamespace(id=30, edit=AsyncMock(), delete=AsyncMock())
        self.send = AsyncMock(return_value=self.message)

    async def edit(self, **kwargs):
        self.edits.append(kwargs)
        self.archived = kwargs.get("archived", self.archived)
        self.locked = kwargs.get("locked", self.locked)

    def get_partial_message(self, message_id):
        return self.message

    async def fetch_message(self, message_id):
        return self.message


async def seeded_sink(store, item, state="Closed"):
    thread = Thread()
    thread.message.embeds = [post_embed(item)]
    bot = SimpleNamespace(get_channel=lambda id: thread)
    sink = DiscordSink(bot, store)
    await store.put(
        "posts",
        guild_id=1,
        repo="example/demo",
        number=42,
        kind="Issue",
        thread_id=20,
        starter_msg_id=20,
        state=state,
    )
    return sink, thread


async def test_comment_echo_edit_delete_and_archiving(store, payload, link):
    sink, thread = await seeded_sink(store, payload["issue"])
    args = (link, payload["issue"], payload["comment"], "issue_comment")
    await sink.comment(*args, "created")
    assert thread.edits[0] == {"archived": False}
    assert thread.archived and not thread.locked
    await sink.comment(*args, "created")
    assert len(await store.all("SELECT * FROM comments")) == 1
    embeds = thread.message.edit.call_args.kwargs["embeds"]
    assert len(embeds) == 2
    assert embeds[1].description.count("A comment") == 1
    payload["comment"]["body"] = "Edited remotely"
    await sink.comment(*args, "edited")
    assert "Edited remotely" in thread.message.edit.call_args.kwargs["embeds"][1].description
    await sink.comment(*args, "deleted")
    await sink.comment(*args, "deleted")
    assert len(thread.message.edit.call_args.kwargs["embeds"]) == 1
    thread.message.delete.assert_not_awaited()
    thread.send.assert_not_awaited()
    assert await store.comment(1, link["repo"], "issue_comment", 99) is None


async def test_deleted_issue_keeps_history_and_locks(store, payload, link):
    sink, thread = await seeded_sink(store, payload["issue"])
    await sink.notice(link, payload["issue"], "Deleted on GitHub.", locked=True, archived=True)
    assert thread.archived and thread.locked
    assert (await store.post(1, link["repo"], 42))["state"] == "Deleted"
    assert "Deleted on GitHub" in thread.message.edit.call_args.kwargs["embeds"][1].description
    thread.send.assert_not_awaited()
    thread.message.delete.assert_not_awaited()


async def test_bot_comment_collapses_and_other_guild_gets_echo(store, payload, link):
    sink, thread = await seeded_sink(store, payload["issue"], "Open")
    payload["comment"]["user"] = {"id": 8, "login": "ci[bot]", "type": "Bot"}
    await sink.comment(link, payload["issue"], payload["comment"], "issue_comment", "created")
    assert "🤖" in thread.message.edit.call_args.kwargs["embeds"][1].description
    assert (await store.comment(1, link["repo"], "issue_comment", 99))["collapsed"]
    await store.put(
        "posts",
        guild_id=2,
        repo=link["repo"],
        number=42,
        kind="Issue",
        thread_id=20,
        starter_msg_id=20,
        state="Open",
    )
    await sink.comment(
        dict(link, guild_id=2), payload["issue"], payload["comment"], "issue_comment", "created"
    )
    assert await store.comment(2, link["repo"], "issue_comment", 99)
    thread.send.assert_not_awaited()
