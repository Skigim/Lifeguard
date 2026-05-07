import unittest


class ConfigFeatureHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_backfill_remembers_feature_when_module_config_exists(self) -> None:
        from lifeguard.cogs.config_cog import ConfigCog
        from lifeguard.features.contracts import FeatureManifest
        from lifeguard.features.registry import FeatureRegistry

        class FakeConfigDoc:
            def __init__(self, exists: bool, data: dict | None = None) -> None:
                self.exists = exists
                self._data = data or {}

            def get(self):
                return self

            def to_dict(self) -> dict:
                return dict(self._data)

        class FakeGuildSettingsDoc(FakeConfigDoc):
            def set(self, payload: dict, merge: bool = False) -> None:
                del merge
                self._data.update(payload)
                self.exists = True

        class FakeCollection:
            def __init__(self, docs: dict[str, FakeConfigDoc]) -> None:
                self.docs = docs

            def document(self, doc_id: str) -> FakeConfigDoc:
                return self.docs.setdefault(doc_id, FakeConfigDoc(False))

        class FakeFirestore:
            def __init__(self) -> None:
                self.collections = {
                    "guild_settings": {
                        "42": FakeGuildSettingsDoc(True, {"guild_id": 42})
                    },
                    "content_review_configs": {
                        "42": FakeConfigDoc(True, {"guild_id": 42})
                    },
                }

            def collection(self, name: str) -> FakeCollection:
                return FakeCollection(self.collections.setdefault(name, {}))

        manifest = FeatureManifest(
            feature_key="content_review",
            display_name="Content Review",
            description="Review workflow",
            emoji="📝",
            requires_setup=True,
            cog_name="ContentReviewCog",
            load_cog=lambda bot: object(),
            build_adapter=lambda bot: object(),
        )
        bot = type(
            "Bot",
            (),
            {
                "lifeguard_features": FeatureRegistry.from_manifests([manifest]),
                "lifeguard_firestore": FakeFirestore(),
            },
        )()

        cog = ConfigCog(bot)  # type: ignore[arg-type]

        entries = cog._feature_entries(42)

        self.assertEqual([entry.feature_key for entry in entries], ["content_review"])
        settings_doc = bot.lifeguard_firestore.collection("guild_settings").document(
            "42"
        )
        self.assertEqual(settings_doc.to_dict()["known_feature_keys"], ["content_review"])