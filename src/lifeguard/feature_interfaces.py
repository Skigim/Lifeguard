from __future__ import annotations

from typing import Protocol

import discord


class SupportsConfigToggle(Protocol):
    """Feature cog interface for config-driven status and toggle operations."""

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


class SupportsContentReviewConfig(Protocol):
    """Content Review config operations used by the shared config shell."""

    async def show_setup(
        self,
        interaction: discord.Interaction,
        *,
        use_send: bool = False,
    ) -> None: ...

    async def show_config_menu(
        self,
        interaction: discord.Interaction,
        *,
        disabled_view: discord.ui.View,
    ) -> None: ...

    async def disable_feature(
        self,
        interaction: discord.Interaction,
        *,
        use_send: bool = False,
    ) -> None: ...


class SupportsVoiceLobbyConfig(SupportsConfigToggle, Protocol):
    """Voice Lobby-specific config operations used by the shared config shell."""

    async def set_entry_channel(
        self,
        interaction: discord.Interaction,
        entry_channel: discord.VoiceChannel,
        *,
        view: discord.ui.View,
    ) -> None: ...

    async def set_category(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel | None,
        *,
        view: discord.ui.View,
    ) -> None: ...

    async def set_defaults(
        self,
        interaction: discord.Interaction,
        name_template: str,
        default_user_limit: str,
    ) -> None: ...

    async def add_creator_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        *,
        view: discord.ui.View,
    ) -> None: ...

    async def remove_creator_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        *,
        view: discord.ui.View,
    ) -> None: ...

    async def clear_creator_roles(
        self,
        interaction: discord.Interaction,
        *,
        view: discord.ui.View,
    ) -> None: ...

    async def add_join_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        *,
        view: discord.ui.View,
    ) -> None: ...

    async def remove_join_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        *,
        view: discord.ui.View,
    ) -> None: ...

    async def clear_join_roles(
        self,
        interaction: discord.Interaction,
        *,
        view: discord.ui.View,
    ) -> None: ...
