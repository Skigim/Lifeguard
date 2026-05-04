from __future__ import annotations

from dataclasses import dataclass

from lifeguard.features.registry import FeatureRegistry
from lifeguard.guild_settings import GuildSettings


@dataclass(frozen=True)
class FeatureEntry:
    feature_key: str
    display_name: str
    description: str
    emoji: str
    status: str


def _humanize_feature_key(feature_key: str) -> str:
    return feature_key.replace("_", " ").title()


def resolve_feature_entries(
    registry: FeatureRegistry,
    settings: GuildSettings,
) -> list[FeatureEntry]:
    entries: dict[str, FeatureEntry] = {}

    for manifest in registry.all_manifests():
        entries[manifest.feature_key] = FeatureEntry(
            feature_key=manifest.feature_key,
            display_name=manifest.display_name,
            description=manifest.description,
            emoji=manifest.emoji,
            status="available",
        )

    for feature_key in settings.known_feature_keys:
        if feature_key in entries:
            continue
        entries[feature_key] = FeatureEntry(
            feature_key=feature_key,
            display_name=_humanize_feature_key(feature_key),
            description="Previously configured feature that is not currently installed.",
            emoji="⚠️",
            status="unavailable",
        )

    return sorted(entries.values(), key=lambda item: item.display_name)
