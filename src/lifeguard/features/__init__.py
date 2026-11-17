"""Feature registry: every Process the loader knows about."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from lifeguard.core.process import Process
from lifeguard.features.github.process import GitHubBridge
from lifeguard.features.greeter import Greeter

if TYPE_CHECKING:
    from lifeguard.bot import LifeguardBot

FEATURES: dict[str, Callable[[LifeguardBot], Process]] = {
    Greeter.name: Greeter,
    GitHubBridge.name: GitHubBridge,
}

# Discord extensions (cogs) that expose each feature's commands.
FEATURE_EXTENSIONS: tuple[str, ...] = (
    "lifeguard.features.greeter",
    "lifeguard.features.github.cogs",
)
