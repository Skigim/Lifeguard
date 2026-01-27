from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lifeguard.db.models import Guild, Item, Player, Zone


async def get_or_create_zone(session: AsyncSession, *, name: str) -> Zone:
    name = name.strip()
    existing = await session.scalar(select(Zone).where(Zone.name == name))
    if existing:
        return existing
    zone = Zone(name=name)
    session.add(zone)
    await session.flush()
    return zone


async def upsert_guild(
    session: AsyncSession,
    *,
    albion_id: str,
    name: str,
    alliance_id: str | None = None,
    alliance_name: str | None = None,
) -> Guild:
    existing = await session.scalar(select(Guild).where(Guild.albion_id == albion_id))
    if existing:
        existing.name = name
        existing.alliance_id = alliance_id
        existing.alliance_name = alliance_name
        await session.flush()
        return existing
    guild = Guild(
        albion_id=albion_id,
        name=name,
        alliance_id=alliance_id,
        alliance_name=alliance_name,
    )
    session.add(guild)
    await session.flush()
    return guild


async def upsert_player(
    session: AsyncSession,
    *,
    albion_id: str,
    name: str,
    guild: Guild | None = None,
) -> Player:
    existing = await session.scalar(select(Player).where(Player.albion_id == albion_id))
    if existing:
        existing.name = name
        existing.guild = guild
        await session.flush()
        return existing
    player = Player(albion_id=albion_id, name=name, guild=guild)
    session.add(player)
    await session.flush()
    return player


async def get_or_create_item(session: AsyncSession, *, item_id: str) -> Item:
    item_id = item_id.strip()
    existing = await session.scalar(select(Item).where(Item.item_id == item_id))
    if existing:
        return existing
    item = Item(item_id=item_id)
    session.add(item)
    await session.flush()
    return item
