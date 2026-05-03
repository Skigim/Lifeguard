from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

import discord
from discord.ext import commands


class FeatureConfigAdapter(Protocol):
    async def show_menu(
        self,
        interaction: discord.Interaction,
        *,
        on_back_to_home: Callable[[discord.Interaction], Awaitable[None]],
    ) -> None: ...

    async def show_status(
        self,
        interaction: discord.Interaction,
        *,
        on_back_to_home: Callable[[discord.Interaction], Awaitable[None]],
    ) -> None: ...

    async def enable(
        self,
        interaction: discord.Interaction,
        *,
        on_back_to_home: Callable[[discord.Interaction], Awaitable[None]] | None = None,
        use_send: bool = False,
    ) -> None: ...

    async def disable(
        self,
        interaction: discord.Interaction,
        *,
        use_send: bool = False,
    ) -> None: ...

    async def show_setup(
        self,
        interaction: discord.Interaction,
        *,
        on_back_to_home: Callable[[discord.Interaction], Awaitable[None]],
        use_send: bool = False,
    ) -> None:
        raise NotImplementedError


@dataclass(frozen=True)
class FeatureManifest:
    feature_key: str
    display_name: str
    description: str
    emoji: str
    requires_setup: bool
    cog_name: str
    load_cog: Callable[[commands.Bot], commands.Cog]
    build_adapter: Callable[[commands.Bot], FeatureConfigAdapter]