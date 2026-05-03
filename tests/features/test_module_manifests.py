import unittest


class ModuleManifestTests(unittest.TestCase):
    def test_existing_modules_export_feature_manifests(self) -> None:
        from lifeguard.features.discovery import discover_feature_manifests

        manifests = discover_feature_manifests("lifeguard.modules")
        feature_keys = sorted(manifest.feature_key for manifest in manifests)

        self.assertEqual(
            feature_keys,
            ["content_review", "time_impersonator", "voice_lobby"],
        )