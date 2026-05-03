from __future__ import annotations

from dataclasses import dataclass

from discord.ext import commands

from lifeguard.features.contracts import FeatureConfigAdapter, FeatureManifest


class DuplicateFeatureKeyError(ValueError):
    pass


@dataclass(frozen=True)
class FeatureRegistry:
    _manifests: dict[str, FeatureManifest]

    @classmethod
    def from_manifests(cls, manifests: list[FeatureManifest]) -> "FeatureRegistry":
        indexed: dict[str, FeatureManifest] = {}
        for manifest in manifests:
            if manifest.feature_key in indexed:
                raise DuplicateFeatureKeyError(manifest.feature_key)
            indexed[manifest.feature_key] = manifest
        return cls(indexed)

    def all_manifests(self) -> list[FeatureManifest]:
        return sorted(self._manifests.values(), key=lambda item: item.display_name)

    def get_manifest(self, feature_key: str) -> FeatureManifest | None:
        return self._manifests.get(feature_key)

    def build_adapter(
        self,
        bot: commands.Bot,
        feature_key: str,
    ) -> FeatureConfigAdapter | None:
        manifest = self.get_manifest(feature_key)
        if manifest is None:
            return None
        return manifest.build_adapter(bot)