from __future__ import annotations

from discord.ext import commands

from lifeguard.features.discovery import discover_feature_manifests
from lifeguard.features.registry import FeatureRegistry


async def register_module_features(
    bot: commands.Bot,
    *,
    package_name: str = "lifeguard.modules",
) -> FeatureRegistry:
    manifests = discover_feature_manifests(package_name)
    registry = FeatureRegistry.from_manifests(manifests)
    for manifest in registry.all_manifests():
        await bot.add_cog(manifest.load_cog(bot))
    return registry
