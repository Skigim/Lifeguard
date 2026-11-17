"""Replay unprocessed deliveries and reconcile changed issue/PR metadata."""

import logging
from datetime import UTC, datetime

from gidgethub import GitHubException

log = logging.getLogger(__name__)


async def recover(bridge):
    cursor = await bridge.store.one("SELECT value FROM bridge_state WHERE key='last_event'")
    # GitHub retains delivery history for three days. First boot inspects all retained entries.
    try:
        async for delivery in bridge.gh.api.getiter(
            "/app/hook/deliveries?per_page=100", jwt=bridge.gh.jwt()
        ):
            processed = await bridge.store.processed(delivery["guid"])
            # Inspect all retained deliveries, including failures older than the cursor.
            if not processed:
                await bridge.gh.api.post(
                    f"/app/hook/deliveries/{delivery['id']}/attempts", jwt=bridge.gh.jwt(), data={}
                )
    except GitHubException:
        log.exception("Could not recover webhook deliveries")
    if not cursor:
        # Without a lower bound, the metadata sweep would import the entire repo history.
        return
    since = float(cursor["value"])
    stamp = datetime.fromtimestamp(max(0, since - 60), UTC).isoformat().replace("+00:00", "Z")
    for link in await bridge.store.links():
        if not bridge.enabled(link["guild_id"]):
            continue
        try:
            async for item in bridge.gh.list_open(
                link["repo"], link["installation_id"], since=stamp
            ):
                async with bridge.locks[(link["repo"], item["number"])]:
                    await bridge.sink.upsert_post(link, item)
        except GitHubException:
            log.exception("Could not reconcile %s", link["repo"])
