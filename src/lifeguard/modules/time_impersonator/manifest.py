from __future__ import annotations

from lifeguard.features.contracts import FeatureManifest
from lifeguard.modules.time_impersonator.cog import TimeImpersonatorCog
from lifeguard.modules.time_impersonator.config_adapter import (
    TimeImpersonatorConfigAdapter,
)


FEATURE_MANIFEST = FeatureManifest(
    feature_key="time_impersonator",
    display_name="Time Impersonator",
    description="Send messages with dynamic Discord timestamps",
    emoji="🕐",
    requires_setup=False,
    cog_name="TimeImpersonatorCog",
    load_cog=lambda bot: TimeImpersonatorCog(bot),
    build_adapter=lambda bot: TimeImpersonatorConfigAdapter(bot),
)
