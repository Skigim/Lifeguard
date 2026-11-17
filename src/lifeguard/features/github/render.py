"""Pure renderers. GitHub text never generates Discord mention notifications."""

import html
import re

import discord


def truncate(text, limit):
    return text if len(text) <= limit else text[: limit - 1] + "…"


def markdown(body, limit=4096):
    # Preserve fenced code verbatim while cleaning prose.
    parts = re.split(r"(```.*?```)", body or "", flags=re.S)
    for i in range(0, len(parts), 2):
        text = re.sub(r"<!--.*?-->", "", parts[i], flags=re.S)
        text = re.sub(
            r'<img\b[^>]*\bsrc=["\']([^"\']+)["\'][^>]*>', r"[Image](\1)", text, flags=re.I
        )
        text = re.sub(r"<(https?://[^>]+)>", r"\1", text)
        text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r"[Image: \1](\2)", text)
        text = re.sub(r"<(?:br\s*/?|/p)>", "\n", text, flags=re.I)
        parts[i] = html.unescape(re.sub(r"<[^>]+>", "", text))
    result = "".join(parts).strip() or "*No description.*"
    result = truncate(result, limit)
    if result.count("```") % 2:
        result = truncate(result, limit - 4) + "\n```"
    return result


def is_bot(user, modes=None):
    login = user.get("login", "")
    mode = (modes or {}).get(login.casefold())
    if mode:
        return mode == "collapse"
    return user.get("type") == "Bot" or login.endswith("[bot]")


def summary(body):
    text = markdown(body, 20000)
    coverage = re.search(
        r"(?:coverage[^\d\n]*)?(\d+(?:\.\d+)?%)(?:[^\n]*?([+-]\d+(?:\.\d+)?%))?", text, re.I
    )
    if coverage:
        return f"Coverage {coverage[1]}" + (f" ({coverage[2]})" if coverage[2] else "")
    text = re.sub(r"\[([^\]]*)\]\([^)]+\)", r"\1", text)
    for line in text.splitlines():
        line = re.sub(r"[*_`#>|~-]", "", line).strip()
        if line:
            return truncate(line, 220)
    return "Updated"


def item_state(item):
    return (
        "Merged"
        if item.get("merged") or item.get("merged_at")
        else ("Closed" if item.get("state") == "closed" else "Open")
    )


def item_kind(item):
    return "PR" if "pull_request" in item or "head" in item else "Issue"


def post_embed(item):
    embed = discord.Embed(
        description=markdown(item.get("body")),
        url=item.get("html_url"),
        title=truncate(item["title"], 256),
    )
    user = item.get("user") or {}
    embed.set_author(name=user.get("login", "GitHub"), icon_url=user.get("avatar_url"))
    footer = f"{item_kind(item)} · {item_state(item)}"
    if item.get("head"):
        footer += f" · {item['head']['ref']} → {item['base']['ref']}"
    embed.set_footer(text=truncate(footer, 1000))
    return embed


def activity_text(comment, kind, collapsed):
    login = discord.utils.escape_markdown((comment.get("user") or {}).get("login", "GitHub"))
    if collapsed:
        return f"🤖 {login} · {summary(comment.get('body'))}"
    text = " ".join(markdown(comment.get("body")).split())
    if kind == "review":
        login += f" · Review ({comment.get('state', 'submitted')})"
    elif kind == "review_comment":
        login += f" · {comment.get('path', '?')}:{comment.get('line') or '?'}"
    return f"**{login}** · {discord.utils.escape_markdown(truncate(text, 140))}"


def starter_embeds(base, rows, notice):
    title = "Recent GitHub activity"
    lines = [truncate(notice, 300)] if notice else []
    for row in rows:
        url = row["activity_url"]
        link = f" · [View]({url})" if url and len(url) <= 300 else ""
        lines.append(f"{truncate(row['activity_text'], 250)}{link}")
    if not lines:
        return [base]
    budget = min(4096, 6000 - len(base) - len(title))
    if budget <= 0:
        return [base]
    shown = []
    for line in lines:
        if sum(len(entry) + 1 for entry in shown) + len(line) > budget:
            break
        shown.append(line)
    if shown:
        return [base, discord.Embed(title=title, description="\n".join(shown))]
    return [base]


def comment_embed(comment, collapsed=False):
    user = comment.get("user") or {}
    login = user.get("login", "GitHub")
    url = comment.get("html_url", "")
    if collapsed:
        return discord.Embed(
            description=f"🤖 {login} · {summary(comment.get('body'))} · [View]({url})"
        )
    embed = discord.Embed(description=markdown(comment.get("body")), url=url)
    embed.set_author(name=login, icon_url=user.get("avatar_url"), url=url or None)
    if comment.get("path"):
        embed.set_footer(
            text=truncate(
                f"{comment['path']}:{comment.get('line') or comment.get('original_line') or '?'}",
                1000,
            )
        )
    elif comment.get("state"):
        embed.set_footer(text=f"Review: {comment['state']}")
    return embed
