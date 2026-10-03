"""Feature registry: every Process the loader knows about."""

from __future__ import annotations

from collections.abc import Callable

from lifeguard.core.process import Process
from lifeguard.features.greeter import Greeter

FEATURES: dict[str, Callable[[], Process]] = {
    Greeter.name: Greeter,
}

# Discord extensions (cogs) that expose each feature's commands.
FEATURE_EXTENSIONS: tuple[str, ...] = ("lifeguard.features.greeter",)
