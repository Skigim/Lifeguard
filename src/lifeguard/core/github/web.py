"""Shared GitHub OAuth endpoints and optional webhook dispatch."""

import secrets
import time
from urllib.parse import urlencode

from aiohttp import web

from .client import RelinkRequired


async def link_url(service, user_id):
    state = secrets.token_urlsafe(32)
    await service.store.put("oauth_states", state=state, discord_id=user_id, created_at=time.time())
    return f"{service.settings.public_url}/oauth/start?state={state}"


def make_app(service, webhook):
    app = web.Application(client_max_size=25 * 1024 * 1024)

    async def health(request):
        return web.json_response({"status": "ok"})

    async def start(request):
        state = request.query.get("state", "")
        row = await service.store.one("SELECT * FROM oauth_states WHERE state=?", (state,))
        if not row or row["created_at"] < time.time() - 600:
            raise web.HTTPBadRequest(text="Expired link. Request a new GitHub link in Discord.")
        query = urlencode(
            {
                "client_id": service.settings.client_id,
                "state": state,
                "redirect_uri": service.settings.public_url + "/oauth/callback",
            }
        )
        raise web.HTTPFound("https://github.com/login/oauth/authorize?" + query)

    async def callback(request):
        row = await service.store.consume_state(request.query.get("state", ""))
        if not row or not request.query.get("code"):
            raise web.HTTPBadRequest(
                text="Invalid or expired authorization. Request a new GitHub link in Discord."
            )
        try:
            tokens = await service.gh.oauth(
                code=request.query["code"],
                redirect_uri=service.settings.public_url + "/oauth/callback",
            )
            user = await service.gh.api.getitem("/user", oauth_token=tokens["access_token"])
            await service.gh.save_user(row["discord_id"], tokens, user)
        except RelinkRequired as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
        return web.Response(
            text="GitHub linked. You can close this tab.", headers={"Cache-Control": "no-store"}
        )

    app.router.add_get("/healthz", health)
    app.router.add_post("/github/webhook", webhook)
    app.router.add_get("/oauth/start", start)
    app.router.add_get("/oauth/callback", callback)
    return app
