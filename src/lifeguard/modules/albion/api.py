"""Albion Data Project API client."""

from __future__ import annotations

from typing import Any

import aiohttp

from lifeguard.modules.albion.models import AlbionDataPrice


async def fetch_prices(
    session: aiohttp.ClientSession,
    *,
    base_url: str,
    items: list[str],
    locations: list[str],
    qualities: list[int],
) -> list[AlbionDataPrice]:
    """Fetch current market prices from Albion Data Project API."""
    items_csv = ",".join(items)
    url = f"{base_url.rstrip('/')}/api/v2/stats/prices/{items_csv}.json"
    params = {
        "locations": ",".join(locations),
        "qualities": ",".join(str(q) for q in qualities),
    }

    async with session.get(url, params=params) as resp:
        resp.raise_for_status()
        payload: list[dict[str, Any]] = await resp.json()

    results: list[AlbionDataPrice] = []
    for row in payload:
        results.append(
            AlbionDataPrice(
                item_id=str(row.get("item_id", "")),
                city=str(row.get("city", "")),
                quality=int(row.get("quality", 0) or 0),
                sell_price_min=int(row.get("sell_price_min", 0) or 0),
                sell_price_min_date=(
                    str(row.get("sell_price_min_date"))
                    if row.get("sell_price_min_date")
                    else None
                ),
                buy_price_max=int(row.get("buy_price_max", 0) or 0),
                buy_price_max_date=(
                    str(row.get("buy_price_max_date"))
                    if row.get("buy_price_max_date")
                    else None
                ),
            )
        )
    return results
