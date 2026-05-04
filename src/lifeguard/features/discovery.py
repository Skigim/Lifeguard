from __future__ import annotations

import importlib
import logging
import pkgutil

from lifeguard.features.contracts import FeatureManifest

LOGGER = logging.getLogger(__name__)


def discover_feature_manifests(
    package_name: str = "lifeguard.modules",
) -> list[FeatureManifest]:
    package = importlib.import_module(package_name)
    manifests: list[FeatureManifest] = []

    for _, module_name, is_pkg in pkgutil.iter_modules(package.__path__):
        if not is_pkg:
            continue

        manifest_module_name = f"{package_name}.{module_name}.manifest"
        try:
            module = importlib.import_module(manifest_module_name)
        except ModuleNotFoundError as exc:
            if exc.name != manifest_module_name:
                raise
            LOGGER.warning("Skipping module without manifest.py: %s", module_name)
            continue

        manifest = getattr(module, "FEATURE_MANIFEST", None)
        if manifest is None:
            LOGGER.warning(
                "Skipping manifest module without FEATURE_MANIFEST: %s",
                module.__name__,
            )
            continue

        manifests.append(manifest)

    return manifests
