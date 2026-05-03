import unittest

from lifeguard.features.contracts import FeatureManifest
from lifeguard.features.registry import FeatureRegistry
from lifeguard.guild_settings import GuildSettings


class AvailabilityTests(unittest.TestCase):
    def test_known_but_missing_feature_is_reported_unavailable(self) -> None:
        from lifeguard.features.availability import resolve_feature_entries

        registry = FeatureRegistry.from_manifests([])
        settings = GuildSettings(guild_id=1, known_feature_keys=["time_impersonator"])

        entries = resolve_feature_entries(registry, settings)

        self.assertEqual(entries[0].feature_key, "time_impersonator")
        self.assertEqual(entries[0].status, "unavailable")
        self.assertEqual(entries[0].display_name, "Time Impersonator")

    def test_discovered_feature_is_reported_available(self) -> None:
        from lifeguard.features.availability import resolve_feature_entries

        manifest = FeatureManifest(
            feature_key="voice_lobby",
            display_name="Voice Lobby",
            description="Temporary voice rooms",
            emoji="🎧",
            requires_setup=False,
            cog_name="VoiceLobbyCog",
            load_cog=lambda bot: object(),
            build_adapter=lambda bot: object(),
        )
        registry = FeatureRegistry.from_manifests([manifest])
        settings = GuildSettings(guild_id=1)

        entries = resolve_feature_entries(registry, settings)

        self.assertEqual(entries[0].feature_key, "voice_lobby")
        self.assertEqual(entries[0].status, "available")