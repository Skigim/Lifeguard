"""Discover installed modules without depending on any one of them."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from pkgutil import iter_modules
from typing import TYPE_CHECKING

from discord import app_commands
from discord.ext import commands

from lifeguard import plugins

if TYPE_CHECKING:
    from lifeguard.bot import LifeguardBot
    from lifeguard.config import Settings
    from lifeguard.core.process import Process

log = logging.getLogger(__name__)


class PluginCog(commands.Cog):
    """Keep the slash command group separate from the global command tree."""

    guild_commands: app_commands.Group


@dataclass(frozen=True)
class Plugin:
    name: str
    process: Callable[[LifeguardBot], Process]
    cog: Callable[[LifeguardBot], PluginCog]
    intents: Callable[[Settings], tuple[str, ...]] = lambda _settings: ()


def discover_plugins() -> list[Plugin]:
    installed = []
    for module in iter_modules(plugins.__path__, prefix=f"{plugins.__name__}."):
        try:
            exported = import_module(module.name).PLUGIN
            if not isinstance(exported, Plugin):
                raise TypeError("PLUGIN must be a Plugin")
            installed.append(exported)
        except Exception:  # noqa: BLE001 - an optional module cannot prevent startup
            log.exception("Skipping optional module %s", module.name)
    return installed
