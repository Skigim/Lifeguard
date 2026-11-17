from types import SimpleNamespace

from lifeguard.features.github.render import is_bot, markdown, post_embed, summary
from lifeguard.features.github.tags import resolve_tags


def test_markdown_and_limits():
    text = markdown(
        "<!-- secret --><b>Hello</b> ![cat](https://example.com/cat)\n```html\n<b>x</b>\n```"
    )
    assert "secret" not in text
    assert "[Image: cat](https://example.com/cat)" in text
    assert "```html\n<b>x</b>\n```" in text
    text = markdown("```\n" + "a" * 5000)
    assert len(text) <= 4096 and text.endswith("```")


def test_bot_overrides_and_summary():
    user = {"login": "codecov[bot]", "type": "Bot"}
    assert is_bot(user)
    assert not is_bot(user, {"codecov[bot]": "human"})
    assert is_bot({"login": "ci"}, {"ci": "collapse"})
    assert summary("<!-- x -->Coverage **84.2%** (+0.3%)") == "Coverage 84.2% (+0.3%)"
    assert summary("### Deployment ready\nMore details") == "Deployment ready"


def test_post_embed(payload):
    embed = post_embed(payload["issue"])
    assert embed.author.name == "alice"
    assert embed.footer.text == "Issue · Open"
    assert "hidden" not in embed.description


def test_tags_priority_override_and_cap():
    tags = [
        SimpleNamespace(id=i, name=name)
        for i, name in enumerate(["Issue", "Open", "BUG", "mapped", "a", "b", "c"])
    ]
    result = resolve_tags(
        "Issue", "Open", ["bug", "custom", "missing", "a", "b"], tags, {"custom": 3}
    )
    assert [tag.id for tag in result] == [0, 1, 2, 3, 4]
