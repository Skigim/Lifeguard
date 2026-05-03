import types
import unittest
from unittest.mock import patch


class FeatureRegistryTests(unittest.TestCase):
    def test_duplicate_feature_keys_raise(self) -> None:
        from lifeguard.features.contracts import FeatureManifest
        from lifeguard.features.registry import DuplicateFeatureKeyError, FeatureRegistry

        manifest_a = FeatureManifest(
            feature_key="voice_lobby",
            display_name="Voice Lobby",
            description="Temporary voice rooms",
            emoji="🎧",
            requires_setup=False,
            cog_name="VoiceLobbyCog",
            load_cog=lambda bot: object(),
            build_adapter=lambda bot: object(),
        )
        manifest_b = FeatureManifest(
            feature_key="voice_lobby",
            display_name="Voice Lobby Duplicate",
            description="Duplicate key",
            emoji="🎧",
            requires_setup=False,
            cog_name="OtherVoiceLobbyCog",
            load_cog=lambda bot: object(),
            build_adapter=lambda bot: object(),
        )

        with self.assertRaises(DuplicateFeatureKeyError):
            FeatureRegistry.from_manifests([manifest_a, manifest_b])

    def test_discovery_imports_manifest_modules(self) -> None:
        package = types.SimpleNamespace(__path__=["modules"])
        manifest_module = types.SimpleNamespace(FEATURE_MANIFEST="manifest-object")

        def fake_import(name: str):
            if name == "lifeguard.modules":
                return package
            if name == "lifeguard.modules.alpha.manifest":
                return manifest_module
            if name == "lifeguard.modules.beta.manifest":
                raise ModuleNotFoundError(name=name)
            raise AssertionError(name)

        with patch("lifeguard.features.discovery.pkgutil.iter_modules") as iter_modules:
            with patch("lifeguard.features.discovery.importlib.import_module") as import_module:
                iter_modules.return_value = [
                    (None, "alpha", True),
                    (None, "beta", True),
                ]
                import_module.side_effect = fake_import

                from lifeguard.features.discovery import discover_feature_manifests

                manifests = discover_feature_manifests("lifeguard.modules")

        self.assertEqual(manifests, ["manifest-object"])
        import_module.assert_any_call("lifeguard.modules.alpha.manifest")
        import_module.assert_any_call("lifeguard.modules.beta.manifest")

    def test_discovery_propagates_transitive_import_errors(self) -> None:
        package = types.SimpleNamespace(__path__=["modules"])

        def fake_import(name: str):
            if name == "lifeguard.modules":
                return package
            if name == "lifeguard.modules.alpha.manifest":
                raise ModuleNotFoundError(name="missing_dependency")
            raise AssertionError(name)

        with patch("lifeguard.features.discovery.pkgutil.iter_modules") as iter_modules:
            with patch("lifeguard.features.discovery.importlib.import_module") as import_module:
                iter_modules.return_value = [(None, "alpha", True)]
                import_module.side_effect = fake_import

                from lifeguard.features.discovery import discover_feature_manifests

                with self.assertRaises(ModuleNotFoundError):
                    discover_feature_manifests("lifeguard.modules")