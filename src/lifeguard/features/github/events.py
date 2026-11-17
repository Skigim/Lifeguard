"""Transport-independent event dispatcher. Sink writes are idempotent by mapping."""

from typing import Protocol


class ForumSink(Protocol):
    async def upsert_post(self, link, item): ...
    async def comment(self, link, item, comment, kind, action): ...
    async def notice(self, link, item, text, *, locked=False, archived=None): ...


class Events:
    def __init__(self, store, gh, sink: ForumSink, enabled, locks):
        self.store, self.gh, self.sink = store, gh, sink
        self.enabled, self.locks = enabled, locks

    async def handle(self, event, payload):
        repo = payload.get("repository", {}).get("full_name", "").lower()
        action = payload.get("action", "")
        if event == "installation_repositories":
            for removed in payload.get("repositories_removed", []):
                await self.store.execute(
                    "DELETE FROM repo_links WHERE repo=? AND installation_id=?",
                    (removed["full_name"].lower(), payload["installation"]["id"]),
                )
            return
        if event not in {
            "issues",
            "pull_request",
            "issue_comment",
            "pull_request_review",
            "pull_request_review_comment",
        }:
            return
        item = payload.get("issue") or payload.get("pull_request")
        if not item:
            return
        number = item["number"]
        async with self.locks[(repo, number)]:
            for link in await self.store.links(repo):
                if not self.enabled(link["guild_id"]):
                    continue
                current = item
                # Issue comment payloads omit PR state/branches.
                if "pull_request" in item and event == "issue_comment":
                    current = await self.gh.get_issue(repo, number, link["installation_id"])
                if event in {"issues", "pull_request"}:
                    if action == "deleted":
                        await self.sink.notice(
                            link, current, "Deleted on GitHub.", locked=True, archived=True
                        )
                        continue
                    if action == "transferred":
                        target = payload.get("changes", {}).get("new_issue", {}).get("html_url")
                        target = target or current.get("html_url", "")
                        await self.sink.notice(
                            link, current, f"Transferred on GitHub: {target}", archived=True
                        )
                        continue
                    await self.sink.upsert_post(link, current)
                    if action in {"closed", "reopened", "ready_for_review", "converted_to_draft"}:
                        label = (
                            "Merged" if current.get("merged") else action.replace("_", " ").title()
                        )
                        actor = payload.get("sender", {}).get("login", "GitHub")
                        await self.sink.notice(link, current, f"{label} by @{actor}")
                else:
                    comment = payload.get("comment") or payload.get("review")
                    if comment:
                        kind = {
                            "pull_request_review": "review",
                            "pull_request_review_comment": "review_comment",
                        }.get(event, "issue_comment")
                        if action != "deleted" and not await self.store.post(
                            link["guild_id"], repo, number
                        ):
                            current = await self.gh.get_issue(repo, number, link["installation_id"])
                            await self.sink.upsert_post(link, current)
                        await self.sink.comment(link, current, comment, kind, action)
