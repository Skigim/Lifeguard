"""Signed webhook ingress for the GitHub bridge."""

import asyncio
import time
from functools import partial

from aiohttp import web
from gidgethub import BadRequest, ValidationFailure, sansio

from lifeguard.core.github.web import make_app as make_github_app


async def webhook(request, bridge):
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


def make_app(bridge):
    return make_github_app(bridge, partial(webhook, bridge=bridge))
