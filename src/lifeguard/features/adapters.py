from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Generic, Protocol, TypeVar, cast

import discord
from discord.ext import commands


class StatusMenuFeatureCog(Protocol):
    async def show_config_status(
        self,
        interaction: discord.Interaction,
        *,
        view: discord.ui.View,
    ) -> None: ...

    async def enable_feature(
        self,
        interaction: discord.Interaction,
        *,
        use_send: bool = False,
    ) -> None: ...

    async def disable_feature(
        self,
        interaction: discord.Interaction,
        *,
        use_send: bool = False,
    ) -> None: ...


CogT = TypeVar("CogT")
StatusCogT = TypeVar("StatusCogT", bound=StatusMenuFeatureCog)
ViewT = TypeVar("ViewT", bound=discord.ui.View)


class CogBackedConfigAdapter(Generic[CogT]):
    def __init__(
        self,
        bot: commands.Bot,
        *,
        cog_name: str,
        missing_cog_message: str,
    ) -> None:
        self._cog = cast(CogT | None, bot.get_cog(cog_name))
        self._missing_cog_message = missing_cog_message

    def _require_cog(self) -> CogT:
        if self._cog is None:
            raise RuntimeError(self._missing_cog_message)
        return self._cog


class StatusMenuConfigAdapter(CogBackedConfigAdapter[StatusCogT], Generic[StatusCogT, ViewT]):
    def __init__(
        self,
        bot: commands.Bot,
        *,
        cog_name: str,
        missing_cog_message: str,
        missing_callback_message: str,
    ) -> None:
        super().__init__(
            bot,
            cog_name=cog_name,
            missing_cog_message=missing_cog_message,
        )
        self._on_back_to_home: Callable[[discord.Interaction], Awaitable[None]] | None = None
        self._missing_callback_message = missing_callback_message

    def _remember_on_back_to_home(
        self,
        on_back_to_home: Callable[[discord.Interaction], Awaitable[None]],
    ) -> None:
        self._on_back_to_home = on_back_to_home

    def _require_on_back_to_home(
        self,
    ) -> Callable[[discord.Interaction], Awaitable[None]]:
        if self._on_back_to_home is None:
            raise RuntimeError(self._missing_callback_message)
        return self._on_back_to_home

    def build_menu_view(self) -> ViewT:
        raise NotImplementedError

    async def show_menu(
        self,
        interaction: discord.Interaction,
        *,
        on_back_to_home: Callable[[discord.Interaction], Awaitable[None]],
    ) -> None:
        self._remember_on_back_to_home(on_back_to_home)
        await self._require_cog().show_config_status(
            interaction,
            view=self.build_menu_view(),
        )

    async def show_status(
        self,
        interaction: discord.Interaction,
        *,
        on_back_to_home: Callable[[discord.Interaction], Awaitable[None]],
    ) -> None:
        await self.show_menu(interaction, on_back_to_home=on_back_to_home)

    async def enable(
        self,
        interaction: discord.Interaction,
        *,
        on_back_to_home: Callable[[discord.Interaction], Awaitable[None]] | None = None,
        use_send: bool = False,
    ) -> None:
        if on_back_to_home is not None:
            self._remember_on_back_to_home(on_back_to_home)
        await self._require_cog().enable_feature(interaction, use_send=use_send)

    async def disable(
        self,
        interaction: discord.Interaction,
        *,
        use_send: bool = False,
    ) -> None:
        await self._require_cog().disable_feature(interaction, use_send=use_send)

    async def show_menu_panel(self, interaction: discord.Interaction) -> None:
        await self.show_menu(
            interaction,
            on_back_to_home=self._require_on_back_to_home(),
        )