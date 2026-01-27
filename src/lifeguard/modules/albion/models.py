"""Albion Online data models."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

from lifeguard.utils import drop_none


@dataclass(frozen=True)
class AlbionDataPrice:
    """Price data from Albion Data Project API."""

    item_id: str
    city: str
    quality: int
    sell_price_min: int
    sell_price_min_date: str | None
    buy_price_max: int
    buy_price_max_date: str | None


@dataclass(frozen=True)
class PlayerDoc:
    """Albion player document for Firestore."""

    name: str
    guild_name: str | None = None
    updated_at: datetime | None = None

    def to_firestore(self) -> dict:
        return drop_none(asdict(self))


@dataclass(frozen=True)
class GuildDoc:
    """Albion guild document for Firestore."""

    name: str
    updated_at: datetime | None = None

    def to_firestore(self) -> dict:
        return drop_none(asdict(self))


@dataclass(frozen=True)
class ZoneDoc:
    """Albion zone document for Firestore."""

    name: str
    updated_at: datetime | None = None

    def to_firestore(self) -> dict:
        return drop_none(asdict(self))


@dataclass(frozen=True)
class ItemRef:
    """Reference to an Albion item with optional quality/quantity."""

    item_id: str
    quantity: int | None = None
    quality: int | None = None

    def to_firestore(self) -> dict:
        return drop_none(asdict(self))


@dataclass(frozen=True)
class BuildDoc:
    """Represents an Albion-style build snapshot.

    Slot names are intentionally plain to match common bot language.
    """

    player_name: str
    guild_name: str | None
    zone_name: str | None
    created_at: datetime

    head: ItemRef | None = None
    chest: ItemRef | None = None
    shoes: ItemRef | None = None

    main_hand: ItemRef | None = None
    off_hand: ItemRef | None = None

    cape: ItemRef | None = None
    bag: ItemRef | None = None
    mount: ItemRef | None = None

    food: ItemRef | None = None
    potion: ItemRef | None = None

    source: str | None = None

    def to_firestore(self) -> dict:
        data: dict = {
            "player_name": self.player_name,
            "guild_name": self.guild_name,
            "zone_name": self.zone_name,
            "created_at": self.created_at,
            "source": self.source,
        }

        def add_item(slot: str, item: ItemRef | None) -> None:
            if item is None:
                return
            data[slot] = item.to_firestore()

        add_item("head", self.head)
        add_item("chest", self.chest)
        add_item("shoes", self.shoes)
        add_item("main_hand", self.main_hand)
        add_item("off_hand", self.off_hand)
        add_item("cape", self.cape)
        add_item("bag", self.bag)
        add_item("mount", self.mount)
        add_item("food", self.food)
        add_item("potion", self.potion)

        return drop_none(data)
