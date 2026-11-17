"""Signed webhook ingress and single-use OAuth state callbacks."""

import asyncio
import time
from urllib.parse import urlencode

from aiohttp import web
from gidgethub import BadRequest, ValidationFailure, sansio

from .gh import RelinkRequired


def make_app(bridge):
    app = web.Application(client_max_size=25 * 1024 * 1024)

    async def health(request):
        return web.json_response({"status": "ok"})

    async def webhook(request):
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not signature.startswith("sha256="):
            raise web.HTTPUnauthorized(text="SHA-256 signature required")
        try:
            event = sansio.Event.from_http(
                request.headers, await request.read(), secret=bridge.settings.webhook_secret
            )
        except (ValidationFailure, BadRequest, ValueError, KeyError) as exc:
            raise web.HTTPUnauthorized(text="Invalid webhook") from exc
        if await bridge.store.processed(event.delivery_id):
            return web.Response(status=200, text="Already processed")
        try:
            bridge.queue.put_nowait((event.delivery_id, time.time(), event.event, event.data))
        except asyncio.QueueFull as exc:
            raise web.HTTPServiceUnavailable(text="Queue full; redeliver later") from exc
        return web.Response(status=202, text="Accepted")

    async def start(request):
        state = request.query.get("state", "")
        row = await bridge.store.one("SELECT * FROM oauth_states WHERE state=?", (state,))
        if not row or row["created_at"] < time.time() - 600:
            raise web.HTTPBadRequest(text="Expired link. Run /github link again.")
        query = urlencode(
            {
                "client_id": bridge.settings.client_id,
                "state": state,
                "redirect_uri": bridge.settings.public_url + "/oauth/callback",
            }
        )
        raise web.HTTPFound("https://github.com/login/oauth/authorize?" + query)

    async def callback(request):
        row = await bridge.store.consume_state(request.query.get("state", ""))
        if not row or not request.query.get("code"):
            raise web.HTTPBadRequest(
                text="Invalid or expired authorization. Run /github link again."
            )
        try:
            tokens = await bridge.gh.oauth(
                code=request.query["code"],
                redirect_uri=bridge.settings.public_url + "/oauth/callback",
            )
            user = await bridge.gh.api.getitem("/user", oauth_token=tokens["access_token"])
            await bridge.gh.save_user(row["discord_id"], tokens, user)
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
