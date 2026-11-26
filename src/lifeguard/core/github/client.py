"""GitHub App installation and user API clients."""

import asyncio
import time
from collections import defaultdict
from datetime import datetime
from urllib.parse import urlencode

import aiohttp
from gidgethub import apps
from gidgethub.aiohttp import GitHubAPI

from .crypto import InvalidToken, TokenCipher


class RelinkRequired(RuntimeError):
    pass


class GitHub:
    def __init__(self, session, settings, store):
        self.session, self.settings, self.store = session, settings, store
        self.cipher = TokenCipher(settings.token_key)
        self.api = GitHubAPI(session, "Lifeguard")
        self.installations = {}
        self.user_locks = defaultdict(asyncio.Lock)

    def jwt(self):
        return apps.get_jwt(app_id=self.settings.app_id, private_key=self.settings.private_key)

    async def installation_token(self, installation):
        cached = self.installations.get(installation)
        if cached and cached[1] > time.time() + 300:
            return cached[0]
        result = await self.api.post(
            f"/app/installations/{installation}/access_tokens", jwt=self.jwt(), data={}
        )
        self.installations[installation] = (
            result["token"],
            datetime.fromisoformat(result["expires_at"].replace("Z", "+00:00")).timestamp(),
        )
        return result["token"]

    async def get_repo_installation(self, repo):
        return await self.api.getitem(f"/repos/{repo}/installation", jwt=self.jwt())

    async def get_issue(self, repo, number, installation):
        token = await self.installation_token(installation)
        item = await self.api.getitem(f"/repos/{repo}/issues/{number}", oauth_token=token)
        if "pull_request" in item:
            item = await self.api.getitem(f"/repos/{repo}/pulls/{number}", oauth_token=token)
        return item

    async def list_open(self, repo, installation, since=None):
        token = await self.installation_token(installation)
        query = {"state": "all" if since else "open", "per_page": 100}
        if since:
            query["since"] = since
        async for item in self.api.getiter(
            f"/repos/{repo}/issues?{urlencode(query)}", oauth_token=token
        ):
            if "pull_request" in item:
                item = await self.get_issue(repo, item["number"], installation)
            yield item

    async def oauth(self, **data):
        async with self.session.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": self.settings.client_id,
                "client_secret": self.settings.client_secret,
                **data,
            },
        ) as response:
            response.raise_for_status()
            result = await response.json()
        if "access_token" not in result:
            raise RelinkRequired("GitHub authorization expired. Please link again.")
        return result

    async def save_user(self, discord_id, tokens, user):
        await self.store.put(
            "user_links",
            discord_id=discord_id,
            gh_id=user["id"],
            gh_login=user["login"],
            access_enc=self.cipher.encrypt(tokens["access_token"]),
            refresh_enc=self.cipher.encrypt(tokens.get("refresh_token")),
            access_exp=time.time() + tokens.get("expires_in", 28800),
            refresh_exp=time.time() + tokens.get("refresh_token_expires_in", 0),
        )

    async def user_token(self, discord_id):
        async with self.user_locks[discord_id]:
            row = await self.store.one("SELECT * FROM user_links WHERE discord_id=?", (discord_id,))
            if row:
                try:
                    token = self.cipher.decrypt(row["access_enc"])
                    if row["access_exp"] > time.time() + 60:
                        return token
                    refresh = self.cipher.decrypt(row["refresh_enc"])
                    if refresh and row["refresh_exp"] > time.time():
                        tokens = await self.oauth(grant_type="refresh_token", refresh_token=refresh)
                        await self.save_user(
                            discord_id, tokens, {"id": row["gh_id"], "login": row["gh_login"]}
                        )
                        return tokens["access_token"]
                except (InvalidToken, RelinkRequired):
                    pass
                await self.store.execute("DELETE FROM user_links WHERE discord_id=?", (discord_id,))
            raise RelinkRequired("Your GitHub account needs to be linked. Use /github link.")

    async def unlink(self, discord_id):
        try:
            token = await self.user_token(discord_id)
        except RelinkRequired:
            return
        async with self.session.delete(
            f"https://api.github.com/applications/{self.settings.client_id}/grant",
            auth=aiohttp.BasicAuth(self.settings.client_id, self.settings.client_secret),
            json={"access_token": token},
            headers={"Accept": "application/vnd.github+json"},
        ) as response:
            if response.status != 404:
                response.raise_for_status()
        await self.store.execute("DELETE FROM user_links WHERE discord_id=?", (discord_id,))

    async def create_issue(self, repo, title, body, token):
        return await self.api.post(
            f"/repos/{repo}/issues", oauth_token=token, data={"title": title, "body": body}
        )

    async def create_comment(self, repo, number, body, token):
        return await self.api.post(
            f"/repos/{repo}/issues/{number}/comments", oauth_token=token, data={"body": body}
        )

    async def set_state(self, repo, number, state, token, reason=None):
        data = {"state": state}
        if reason:
            data["state_reason"] = reason
        return await self.api.patch(f"/repos/{repo}/issues/{number}", oauth_token=token, data=data)

    def comment_path(self, row):
        if row["gh_kind"] == "review":
            return f"/repos/{row['repo']}/pulls/{row['number']}/reviews/{row['gh_comment_id']}"
        prefix = "issues" if row["gh_kind"] == "issue_comment" else "pulls"
        return f"/repos/{row['repo']}/{prefix}/comments/{row['gh_comment_id']}"

    async def get_comment(self, row, token):
        return await self.api.getitem(self.comment_path(row), oauth_token=token)

    async def edit_comment(self, row, body, token):
        method = self.api.put if row["gh_kind"] == "review" else self.api.patch
        return await method(self.comment_path(row), oauth_token=token, data={"body": body})

    async def delete_comment(self, row, token):
        await self.api.delete(self.comment_path(row), oauth_token=token)
