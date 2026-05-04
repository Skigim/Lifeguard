import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from lifeguard.features.contracts import FeatureManifest
from lifeguard.config import Config


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

    async def test_setup_hook_skips_firestore_backed_features_when_firestore_disabled(
        self,
    ) -> None:
        from lifeguard.bot import create_bot

        config = Config(
            bot_env="test",
            discord_token=None,
            guild_id=None,
            test_guild_id=None,
            command_prefix="!",
            log_level="INFO",
            firebase_enabled=False,
            firebase_credentials_path=None,
            firebase_project_id=None,
        )

        fake_session = SimpleNamespace(close=AsyncMock())
        core_cog = object()
        added_cogs: list[object] = []

        with patch("aiohttp.ClientSession", return_value=fake_session):
            with patch("lifeguard.firestore_client.init_firestore", return_value=None):
                with patch("lifeguard.bot._load_core_cog", return_value=core_cog):
                    with patch("lifeguard.bot._load_config_cog") as load_config_cog:
                        with patch(
                            "lifeguard.bot.register_module_features",
                            new_callable=AsyncMock,
                        ) as register_module_features:
                            bot = create_bot(config)
                            bot.add_cog = AsyncMock(
                                side_effect=lambda cog: added_cogs.append(cog)
                            )

                            await bot.setup_hook()

        self.assertIsNone(getattr(bot, "lifeguard_firestore", None))
        self.assertEqual(added_cogs, [core_cog])
        load_config_cog.assert_not_called()
        register_module_features.assert_not_awaited()