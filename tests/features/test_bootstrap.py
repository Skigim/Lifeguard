import unittest
from unittest.mock import patch

from lifeguard.features.contracts import FeatureManifest


class _FakeBot:
    def __init__(self) -> None:
        self.added_cogs: list[object] = []

    async def add_cog(self, cog: object) -> None:
        self.added_cogs.append(cog)


class BootstrapTests(unittest.IsolatedAsyncioTestCase):
    async def test_register_module_features_loads_discovered_cogs(self) -> None:
        fake_bot = _FakeBot()
        fake_cog = object()
        manifest = FeatureManifest(
            feature_key="time_impersonator",
            display_name="Time Impersonator",
            description="Dynamic timestamps",
            emoji="🕐",
            requires_setup=False,
            cog_name="TimeImpersonatorCog",
            load_cog=lambda bot: fake_cog,
            build_adapter=lambda bot: object(),
        )

        with patch(
            "lifeguard.features.bootstrap.discover_feature_manifests",
            return_value=[manifest],
        ):
            from lifeguard.features.bootstrap import register_module_features

            registry = await register_module_features(fake_bot)

        self.assertEqual(fake_bot.added_cogs, [fake_cog])
        self.assertEqual(registry.get_manifest("time_impersonator"), manifest)