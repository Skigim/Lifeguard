import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import discord
import pytest
from cryptography.fernet import Fernet

from lifeguard import plugins
from lifeguard.bot import LifeguardBot
from lifeguard.config import ConfigError, GitHubSettings, Settings, load_settings
from lifeguard.core.github.service import GitHubService
from lifeguard.core.loader import Loader, ProcessDisabled
from lifeguard.plugins.local_review import process as local_review_process
from lifeguard.plugins.local_review.cog import ISSUE_REQUEST, LocalReviewCog
from lifeguard.plugins.local_review.process import HookSettings, LocalReview
from lifeguard.plugins.local_review.references import References


def test_local_review_intent_is_opt_in():
    env = {"DISCORD_TOKEN": "test"}
    assert not LifeguardBot(load_settings(env)).intents.message_content
    settings = load_settings(dict(env, LOCAL_REVIEW_TOKEN="agent-token"))
    assert HookSettings.from_env(settings.environ) == HookSettings(token="agent-token")
    assert LifeguardBot(settings).intents.message_content
    with pytest.raises(ConfigError, match="LOCAL_REVIEW_PORT"):
        HookSettings.from_env(
            dict(env, LOCAL_REVIEW_TOKEN="agent-token", LOCAL_REVIEW_PORT="65536")
        )


async def test_optional_commands_follow_guild_enablement_and_module_removal(tmp_path, monkeypatch):
    settings = Settings(
        "test",
        "test",
        guild_id=1,
        database_path=str(tmp_path / "bot.db"),
        environ={"LOCAL_REVIEW_TOKEN": "agent-token"},
    )
    monkeypatch.setattr(LocalReview, "start", AsyncMock())
    monkeypatch.setattr(LocalReview, "stop", AsyncMock())
    bot = LifeguardBot(settings)
    sync = AsyncMock(return_value=[])
    monkeypatch.setattr(bot.tree, "sync", sync)
    first, second = discord.Object(id=1), discord.Object(id=2)
    try:
        await bot.setup_hook()
        assert bot.tree.get_command("lg") is None
        assert bot.tree.get_command("lg", guild=first) is None
        assert await bot.set_feature_enabled("local-review", 1, True)
        group = bot.tree.get_command("lg", guild=first)
        assert {command.name for command in group.commands} == {"hook", "setup"}
        assert group.get_command("setup").parameters[0].name == "repo"
        assert bot.tree.get_command("lg", guild=second) is None
        assert await bot.set_feature_enabled("local-review", 2, True)
        assert await bot.set_feature_enabled("local-review", 1, False)
        assert bot.tree.get_command("lg", guild=first) is None
        assert bot.tree.get_command("comment", guild=first) is not None
        assert bot.tree.get_command("lg", guild=second) is group
        with pytest.raises(ProcessDisabled):
            bot.loader.require("local-review", 1)
        assert bot.loader.require("local-review", 2) is not None
    finally:
        await bot.close()

    monkeypatch.setattr(plugins, "__path__", [])
    restarted = LifeguardBot(settings)
    sync = AsyncMock(return_value=[])
    monkeypatch.setattr(restarted.tree, "sync", sync)
    try:
        await restarted.setup_hook()
        assert "local-review" not in restarted.loader.names
        assert not restarted.intents.message_content
        assert restarted.tree.get_command("lg", guild=second) is None
        assert restarted.tree.get_command("feature", guild=first) is not None
        assert restarted.tree.get_command("comment", guild=first) is not None
        assert restarted.loader.command_guilds() == set()
        sync.assert_any_await(guild=second)
    finally:
        await restarted.close()


async def test_mention_handoff_and_github_write_without_bridge(unused_tcp_port_factory):
    loader = Loader()
    hook_port, oauth_port = unused_tcp_port_factory(), unused_tcp_port_factory()
    settings = Settings(
        "test",
        "test",
        database_path=":memory:",
        github=GitHubSettings(
            app_id="1",
            private_key="unused",
            webhook_secret="secret",
            client_id="client",
            client_secret="secret",
            public_url="https://example.com",
            token_key=Fernet.generate_key().decode(),
            web_host="127.0.0.1",
            web_port=oauth_port,
        ),
        environ={"LOCAL_REVIEW_TOKEN": "agent-token", "LOCAL_REVIEW_PORT": str(hook_port)},
    )
    service = GitHubService(settings)
    bot = SimpleNamespace(
        user=SimpleNamespace(id=99), settings=settings, loader=loader, github_service=service
    )
    reviewer = LocalReview(bot)
    loader.register(LocalReview.name, lambda: reviewer)
    try:
        await loader.enable(LocalReview.name, 1)
        store, gh = service.store, service.gh
        gh.user_token = AsyncMock(return_value="linked-user-token")
        gh.create_issue = AsyncMock(
            return_value={"number": 42, "html_url": "https://github.com/example/project/issues/42"}
        )
        gh.get_repo_installation = AsyncMock(return_value={"id": 7})
        await store.put("user_links", discord_id=2)
        cog = LocalReviewCog(bot)
        deferred = SimpleNamespace(
            defer=AsyncMock(),
            type=discord.InteractionResponseType.deferred_channel_message,
        )
        deferred.is_done = lambda: deferred.defer.await_count > 0
        admin = SimpleNamespace(
            guild_id=1,
            permissions=discord.Permissions(manage_guild=True),
            response=deferred,
            edit_original_response=AsyncMock(return_value=SimpleNamespace(delete=AsyncMock())),
        )
        await cog.setup_agent(admin, repo="Example/Project")
        gh.get_repo_installation.assert_awaited_once_with("example/project")
        deferred.defer.assert_awaited_once_with(ephemeral=True)
        assert "Default repository set" in admin.edit_original_response.await_args.kwargs["content"]

        response = SimpleNamespace(is_done=lambda: False, send_message=AsyncMock())
        interaction = SimpleNamespace(guild_id=1, response=response, user=SimpleNamespace(id=2))
        await cog.hook(interaction)
        assert f"http://127.0.0.1:{hook_port}" in response.send_message.await_args.args[0]
        assert "agent-token" not in response.send_message.await_args.args[0]
        await cog.setup_agent(interaction)
        assert response.send_message.await_args.kwargs["ephemeral"] is True
        view = response.send_message.await_args.kwargs["view"]
        link_button = next(item for item in view.children if item.label == "Link GitHub")
        await link_button.callback(interaction)
        oauth_view = response.send_message.await_args.kwargs["view"]
        oauth_path = oauth_view.children[0].url.removeprefix(settings.github.public_url)

        guild = SimpleNamespace(id=1)
        thread = MagicMock(spec=discord.Thread, guild=guild, id=20, parent_id=10)
        thread.name = "Export discussion"

        async def history(**kwargs):
            assert kwargs["before"] is mention
            for content, is_bot in (
                ("CSV loses the last filtered row.", False),
                ("Bot log", True),
                ("Export discussion begins.", False),
            ):
                yield SimpleNamespace(
                    type=discord.MessageType.default,
                    content=content,
                    author=SimpleNamespace(bot=is_bot),
                    is_system=lambda: False,
                )

        thread.history.side_effect = history
        mention = MagicMock(
            spec=discord.Message,
            id=30,
            guild=guild,
            channel=thread,
            author=SimpleNamespace(id=2, bot=False),
            webhook_id=None,
            jump_url="https://discord.com/channels/1/20/30",
        )
        mention.content = "<@99>, review this discussion thread and add relevant issues to Github"

        url = f"http://127.0.0.1:{hook_port}"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as client:
            async with client.get(f"{url}/v1/health") as response:
                assert response.status == 401
            headers = {"Authorization": "Bearer agent-token"}
            async with client.get(f"{url}/v1/health", headers=headers) as response:
                assert await response.json() == {"status": "ok"}
            async with client.get(
                f"http://127.0.0.1:{oauth_port}{oauth_path}", allow_redirects=False
            ) as response:
                assert response.status == 302
                assert response.headers["Location"].startswith("https://github.com/login/oauth/")
            async with asyncio.timeout(8), asyncio.TaskGroup() as tasks:
                tasks.create_task(cog.on_message(mention))
                async with client.post(f"{url}/v1/jobs/next", headers=headers) as response:
                    assert response.status == 200
                    job = await response.json()
                assert job["action"] == "review_thread_for_github_issues"
                assert "prompt" not in job
                assert job["repo"] == "example/project"
                assert job["thread"] == {
                    "title": "Export discussion",
                    "messages": ["Export discussion begins.", "CSV loses the last filtered row."],
                }
                result_url = f"{url}/v1/jobs/{job['id']}/result"
                draft = {"title": "Fix CSV export", "body": "Keep the last filtered row."}
                async with client.post(
                    result_url, headers=headers, json={"issues": [draft], "repo": "example/other"}
                ) as response:
                    assert response.status == 422
                gh.create_issue.assert_not_awaited()
                async with client.post(
                    result_url, headers=headers, json={"issues": [draft]}
                ) as response:
                    assert response.status == 204
            async with client.post(result_url, headers=headers, json={"issues": []}) as response:
                assert response.status == 404
            await cog.on_message(mention)

            original = MagicMock(spec=discord.Message, author=SimpleNamespace(id=99, bot=True))
            original.content = "Preserve the final matching CSV row."
            mention.id = 31
            mention.type = discord.MessageType.reply
            mention.reference = SimpleNamespace(message_id=45, guild_id=1, resolved=original)
            gh.get_pull_request = AsyncMock()
            gh.create_comment = AsyncMock(return_value={"html_url": "https://example.com/comment"})

            async def follow_up(prompt, action, *, text="", pr_number=None):
                mention.content = prompt
                async with asyncio.timeout(5), asyncio.TaskGroup() as tasks:
                    tasks.create_task(cog.on_message(mention))
                    async with client.post(
                        f"{url}/v1/jobs/next?include_references=true", headers=headers
                    ) as response:
                        assert response.status == 200
                        job = await response.json()
                    assert job["action"] == "respond_to_reference"
                    assert job["prompt"] == prompt
                    assert job["reference"] == {
                        "kind": "reply",
                        "content": original.content,
                        "mentioned": False,
                    }
                    async with client.post(
                        f"{url}/v1/jobs/{job['id']}/result",
                        headers=headers,
                        json={
                            "action": action,
                            "text": text,
                            "repo": None,
                            "pr_number": pr_number,
                            "issues": [],
                        },
                    ) as response:
                        assert response.status == 204

            assert "example/project#42" in thread.send.await_args.args[0]
            thread.send.reset_mock()
            thread.typing.reset_mock()
            await follow_up("This is what Lifeguard said", "ignore")
            thread.send.assert_not_awaited()
            thread.typing.assert_not_called()
            await follow_up("What makes that a bug?", "reply", text="The export loses data.")
            assert thread.send.await_args.args[0] == "The export loses data."
            await follow_up(
                "Could you drop that on PR #7 or PR #12?",
                "post_pr_comment",
                text=original.content,
                pr_number=7,
            )
            assert "Which pull request" in thread.send.await_args.args[0]
            gh.create_comment.assert_not_awaited()
            followup_prompt = "That would make a good comment on PR #7. Can you put it there?"
            await follow_up(followup_prompt, "post_pr_comment", text=original.content, pr_number=7)
            await follow_up(followup_prompt, "post_pr_comment", text=original.content, pr_number=7)
            gh.create_comment.assert_awaited_once_with(
                "example/project", 7, original.content, "linked-user-token"
            )
            assert "Posted a [comment" in thread.send.await_args.args[0]

        assert all(call.args == (2,) for call in gh.user_token.await_args_list)
        gh.create_issue.assert_awaited_once_with(
            "example/project",
            "Fix CSV export",
            "Keep the last filtered row.\n\nSource discussion: https://discord.com/channels/1/20/30",
            "linked-user-token",
        )
    finally:
        await loader.shutdown()


@pytest.mark.parametrize("inside_thread", [True, False])
async def test_free_form_mention_replies_without_github(
    inside_thread, unused_tcp_port, monkeypatch
):
    monkeypatch.setattr(local_review_process, "POLL_TIMEOUT", 0.2)
    loader = Loader()
    settings = Settings(
        "test",
        "test",
        environ={"LOCAL_REVIEW_TOKEN": "agent-token", "LOCAL_REVIEW_PORT": str(unused_tcp_port)},
    )
    bot = SimpleNamespace(user=SimpleNamespace(id=99), settings=settings, loader=loader)
    reviewer = LocalReview(bot)
    loader.register(LocalReview.name, lambda: reviewer)
    await loader.enable(LocalReview.name, 1)
    try:
        guild = SimpleNamespace(id=1)
        channel = MagicMock(spec=discord.Thread if inside_thread else discord.TextChannel)
        channel.name = "Export discussion"
        prompt = "Review this thread and recommend a milestone title and checklist."
        mention = MagicMock(
            spec=discord.Message,
            content=f"<@99> {prompt}",
            guild=guild,
            channel=channel,
            author=SimpleNamespace(id=2, bot=False),
            webhook_id=None,
        )

        async def history(**kwargs):
            assert kwargs["before"] is mention
            yield SimpleNamespace(
                type=discord.MessageType.default,
                content="CSV loses the last filtered row.",
                author=SimpleNamespace(bot=False),
                is_system=lambda: False,
            )

        channel.history.side_effect = history
        url = f"http://127.0.0.1:{unused_tcp_port}"
        headers = {"Authorization": "Bearer agent-token"}
        suggested = "**Milestone: Reliable CSV exports**\n- Keep the last filtered row."
        async with (
            aiohttp.ClientSession(headers=headers) as client,
            asyncio.timeout(5),
            asyncio.TaskGroup() as tasks,
        ):
            tasks.create_task(LocalReviewCog(bot).on_message(mention))
            async with client.post(f"{url}/v1/jobs/next") as response:
                assert response.status == 204
            async with client.post(f"{url}/v1/jobs/next?include_replies=true") as response:
                assert response.status == 200
                job = await response.json()
            assert job["action"] == "respond_to_prompt"
            assert job["prompt"] == prompt
            assert "repo" not in job
            if inside_thread:
                assert job["thread"] == {
                    "title": "Export discussion",
                    "messages": ["CSV loses the last filtered row."],
                }
            else:
                assert job["thread"] is None
                channel.history.assert_not_called()
            result_url = f"{url}/v1/jobs/{job['id']}/result"
            async with client.post(result_url, json={"issues": []}) as response:
                assert response.status == 422
            async with client.post(result_url, json={"reply": suggested}) as response:
                assert response.status == 204
        assert channel.send.await_args.args[0] == suggested
        assert not channel.send.await_args.kwargs["allowed_mentions"].everyone
    finally:
        await loader.shutdown()


@pytest.mark.parametrize(
    ("prompt", "action", "text", "pr_number"),
    [
        ("You can ping @Lifeguard. It’s not gonna think so good.", "react", "🤨", None),
        ("You can ping @Lifeguard for help with a thread.", "ignore", "", None),
        ("I wonder if @Lifeguard can post on PR #7.", "post_pr_comment", "Hello", 7),
    ],
)
async def test_inline_mention_routes_conversation_only(
    prompt, action, text, pr_number, unused_tcp_port
):
    loader = Loader()
    settings = Settings(
        "test",
        "test",
        environ={"LOCAL_REVIEW_TOKEN": "agent-token", "LOCAL_REVIEW_PORT": str(unused_tcp_port)},
    )
    bot = SimpleNamespace(user=SimpleNamespace(id=99), settings=settings, loader=loader)
    reviewer = LocalReview(bot)
    loader.register(LocalReview.name, lambda: reviewer)
    await loader.enable(LocalReview.name, 1)
    try:
        message = MagicMock(
            spec=discord.Message,
            content=prompt.replace("@Lifeguard", "<@99>"),
            mentions=[bot.user],
            guild=SimpleNamespace(id=1),
            channel=MagicMock(spec=discord.TextChannel),
            author=SimpleNamespace(id=2, bot=False),
            reference=None,
            webhook_id=None,
        )
        cog = LocalReviewCog(bot)
        cog.post_pr_comment = AsyncMock()
        url = f"http://127.0.0.1:{unused_tcp_port}"
        headers = {"Authorization": "Bearer agent-token"}
        async with (
            aiohttp.ClientSession(headers=headers) as client,
            asyncio.timeout(5),
            asyncio.TaskGroup() as tasks,
        ):
            tasks.create_task(cog.on_message(message))
            async with client.post(f"{url}/v1/jobs/next?include_references=true") as response:
                assert response.status == 200
                job = await response.json()
            assert job["action"] == "respond_to_reference"
            assert job["prompt"] == prompt
            assert job["reference"] == {"kind": "mention", "content": None, "mentioned": False}
            assert job["thread"] is None
            result_url = f"{url}/v1/jobs/{job['id']}/result"
            result = dict(action=action, text=text, repo=None, pr_number=pr_number, issues=[])
            if action == "react":
                async with client.post(result_url, json=dict(result, text="🤨🤨")) as response:
                    assert response.status == 422
            async with client.post(result_url, json=result) as response:
                assert response.status == 204
        if action == "react":
            message.add_reaction.assert_awaited_once_with(text)
        else:
            message.add_reaction.assert_not_awaited()
        message.channel.send.assert_not_awaited()
        cog.post_pr_comment.assert_not_awaited()
    finally:
        await loader.shutdown()


def test_explicit_issue_requests_and_negative_prompts():
    assert ISSUE_REQUEST.fullmatch("Could you file GitHub issues from this thread?")
    assert ISSUE_REQUEST.fullmatch("Create a GitHub issue repo:example/project")["repo"] == (
        "example/project"
    )
    assert not ISSUE_REQUEST.fullmatch("Review this thread and don't add any issues to GitHub")


@pytest.mark.parametrize("kind", ["reply", "quote", "link", "forward"])
async def test_resolve_own_reference_and_separate_the_new_prompt(kind):
    guild = SimpleNamespace(id=1)
    channel = MagicMock(spec=discord.Thread, id=20, guild=guild)
    original = MagicMock(
        spec=discord.Message,
        id=30,
        channel=channel,
        guild=guild,
        author=SimpleNamespace(id=99, bot=True),
        content="Keep the last filtered row.",
    )
    message = MagicMock(
        spec=discord.Message,
        guild=guild,
        channel=channel,
        type=discord.MessageType.default,
        reference=None,
    )
    tracker = References()
    tracker.remember(original)
    prompt = "Can you explain the impact?"
    if kind in {"reply", "forward"}:
        message.reference = SimpleNamespace(
            message_id=30,
            channel_id=20,
            guild_id=1,
            resolved=original,
            type=discord.MessageReferenceType.default,
        )
        if kind == "reply":
            message.type = discord.MessageType.reply
        else:
            message.reference.type = discord.MessageReferenceType.forward
            message.message_snapshots = [SimpleNamespace(content=original.content)]
        text = prompt
    elif kind == "link":
        text = f"{prompt}\nhttps://discord.com/channels/1/20/30"
    else:
        original.channel = MagicMock(spec=discord.Thread, id=21, guild=guild)
        text = f"> {original.content}\n\n{prompt}"
    reference, authored = await tracker.resolve(message, 99, text)
    assert authored == prompt
    assert reference.kind == kind
    assert reference.content == original.content
    channel.fetch_message.assert_not_awaited()
