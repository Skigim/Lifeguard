import asyncio
from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from lifeguard.features.github.cogs import BridgeError, CommentModal, DeleteView


@pytest.fixture
async def actions(store):
    await store.put("repo_links", guild_id=1, repo="example/demo", forum_id=10, installation_id=12)
    await store.put(
        "posts",
        guild_id=1,
        repo="example/demo",
        number=42,
        kind="Issue",
        thread_id=20,
        starter_msg_id=20,
        state="Open",
    )
    await store.put(
        "comments",
        guild_id=1,
        repo="example/demo",
        number=42,
        gh_comment_id=99,
        gh_kind="issue_comment",
        gh_author_id=7,
        thread_id=20,
        message_id=30,
        collapsed=0,
    )
    await store.put("user_links", discord_id=5, gh_id=7, gh_login="alice")
    proc = SimpleNamespace(store=store, locks=defaultdict(asyncio.Lock))
    proc.gh = SimpleNamespace(
        user_token=AsyncMock(return_value="token"),
        edit_comment=AsyncMock(return_value={"id": 99, "body": "changed"}),
        delete_comment=AsyncMock(),
        create_comment=AsyncMock(return_value={"id": 100, "body": "new"}),
    )
    proc.sink = SimpleNamespace(comment=AsyncMock())
    bot = SimpleNamespace(loader=SimpleNamespace(require=lambda name, guild: proc))
    interaction = SimpleNamespace(
        guild_id=1,
        channel_id=20,
        user=SimpleNamespace(id=5),
        response=SimpleNamespace(defer=AsyncMock(), is_done=lambda: True),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    return bot, proc, interaction


async def test_modal_defers_then_writes_and_mirrors(actions):
    bot, proc, interaction = actions
    modal = CommentModal(bot, message_id=30, body="changed")
    await modal.on_submit(interaction)
    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    assert proc.gh.edit_comment.call_args.args[1:] == ("changed", "token")
    assert proc.sink.comment.call_args.args[-2:] == ("issue_comment", "edited")
    modal = CommentModal(bot, body="new")
    await modal.on_submit(interaction)
    proc.gh.create_comment.assert_awaited_once_with("example/demo", 42, "new", "token")
    assert proc.sink.comment.call_args.args[-2:] == ("issue_comment", "created")


async def test_delete_requires_confirmation_and_rechecks_author(actions):
    bot, proc, interaction = actions
    view = DeleteView(bot, 5, 30)
    proc.gh.delete_comment.assert_not_awaited()
    await proc.store.execute("UPDATE user_links SET gh_id=8 WHERE discord_id=5")
    with pytest.raises(BridgeError, match="author"):
        await view.confirm.callback(interaction)
    proc.gh.delete_comment.assert_not_awaited()
    await proc.store.execute("UPDATE user_links SET gh_id=7 WHERE discord_id=5")
    view = DeleteView(bot, 5, 30)
    await view.confirm.callback(interaction)
    proc.gh.delete_comment.assert_awaited_once()
    assert proc.sink.comment.call_args.args[-2:] == ("issue_comment", "deleted")
    await view.confirm.callback(interaction)
    assert proc.gh.delete_comment.await_count == 1
