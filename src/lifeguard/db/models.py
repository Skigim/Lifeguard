from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lifeguard.db.base import Base


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    albion_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64), index=True)

    guild_id: Mapped[int | None] = mapped_column(ForeignKey("guilds.id"), nullable=True)
    guild = relationship("Guild", back_populates="players")


class Guild(Base):
    __tablename__ = "guilds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    albion_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), index=True)

    alliance_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    alliance_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    players = relationship("Player", back_populates="guild")


class Zone(Base):
    __tablename__ = "zones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Albion item type string, e.g. T8_2H_DUALSWORD@2
    item_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)

    # Optional human label (if you later load metadata dumps)
    label: Mapped[str | None] = mapped_column(String(128), nullable=True)


class Build(Base):
    """A build snapshot for a player at a point in time.

    Stores one row per equipment slot. This keeps it flexible for future slots.
    """

    __tablename__ = "builds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc)
    )

    player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"), nullable=True)
    player = relationship("Player")

    # Optional source reference (e.g., a kill event id)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    slots = relationship("BuildSlot", back_populates="build", cascade="all, delete-orphan")


class BuildSlot(Base):
    __tablename__ = "build_slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    build_id: Mapped[int] = mapped_column(ForeignKey("builds.id"), index=True)
    build = relationship("Build", back_populates="slots")

    # Examples: mainhand, offhand, head, armor, shoes, cape, bag, mount, potion, food
    slot: Mapped[str] = mapped_column(String(32), index=True)

    item_db_id: Mapped[int | None] = mapped_column(ForeignKey("items.id"), nullable=True)
    item = relationship("Item")

    # Captured attributes (often available in kill/event payloads)
    count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (Index("ix_build_slots_build_slot", "build_id", "slot", unique=True),)


class KillEvent(Base):
    """A killmail-like event captured from Game Info events."""

    __tablename__ = "kill_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    occurred_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)

    zone_id: Mapped[int | None] = mapped_column(ForeignKey("zones.id"), nullable=True)
    zone = relationship("Zone")

    killer_player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"), nullable=True)
    killer_player = relationship("Player", foreign_keys=[killer_player_id])

    victim_player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"), nullable=True)
    victim_player = relationship("Player", foreign_keys=[victim_player_id])

    total_victim_kill_fame: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
