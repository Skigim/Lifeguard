import unittest

from lifeguard.features.availability import FeatureEntry


class ConfigShellViewTests(unittest.IsolatedAsyncioTestCase):
    async def test_top_level_view_builds_select_options_from_feature_entries(self) -> None:
        from lifeguard.cogs.config_views import ConfigHomeView

        entries = [
            FeatureEntry(
                feature_key="time_impersonator",
                display_name="Time Impersonator",
                description="Send messages with dynamic Discord timestamps",
                emoji="🕐",
                status="available",
            ),
            FeatureEntry(
                feature_key="voice_lobby",
                display_name="Voice Lobby",
                description="Temporary voice lobbies created from an entry channel",
                emoji="🎧",
                status="available",
            ),
        ]

        view = ConfigHomeView(cog=None, feature_entries=entries)  # type: ignore[arg-type]
        select = next(item for item in view.children if getattr(item, "options", None))

        self.assertEqual(
            [option.value for option in select.options],
            ["time_impersonator", "voice_lobby"],
        )

    async def test_autocomplete_filters_registry_entries(self) -> None:
        from lifeguard.cogs.config_cog import build_feature_autocomplete_choices

        entries = [
            FeatureEntry(
                feature_key="time_impersonator",
                display_name="Time Impersonator",
                description="Send messages with dynamic Discord timestamps",
                emoji="🕐",
                status="available",
            ),
            FeatureEntry(
                feature_key="voice_lobby",
                display_name="Voice Lobby",
                description="Temporary voice lobbies created from an entry channel",
                emoji="🎧",
                status="available",
            ),
        ]

        choices = build_feature_autocomplete_choices(entries, current="voice")

        self.assertEqual([choice.value for choice in choices], ["voice_lobby"])

    async def test_unavailable_feature_keeps_back_navigation(self) -> None:
        from lifeguard.cogs.config_cog import ConfigCog
        from lifeguard.features.registry import FeatureRegistry

        class _FakeResponse:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            async def edit_message(self, **kwargs) -> None:
                self.calls.append(kwargs)

        class _FakeInteraction:
            def __init__(self) -> None:
                self.guild = type("Guild", (), {"id": 1})()
                self.response = _FakeResponse()

        class _FakeFirestore:
            def collection(self, name: str):
                raise AssertionError(name)

        bot = type(
            "Bot",
            (),
            {
                "lifeguard_features": FeatureRegistry.from_manifests([]),
                "lifeguard_firestore": _FakeFirestore(),
            },
        )()
        cog = ConfigCog(bot)  # type: ignore[arg-type]
        interaction = _FakeInteraction()

        await cog._dispatch_feature_menu(interaction, "time_impersonator")

        self.assertEqual(len(interaction.response.calls), 1)
        self.assertIsNotNone(interaction.response.calls[0]["view"])