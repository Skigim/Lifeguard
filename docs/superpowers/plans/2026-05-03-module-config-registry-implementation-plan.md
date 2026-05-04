# Module Config Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hardcoded module config routing with auto-discovered module manifests and a shared runtime feature registry while preserving the shared `/config`, `/enable-feature`, and `/disable-feature` commands.

**Architecture:** Add a small `lifeguard.features` platform that discovers module manifests, loads module cogs, resolves feature adapters, and computes feature availability from registry state plus shared guild settings. Migrate existing modules onto manifests and module-owned config adapters, then refactor the shared config shell to render from registry metadata instead of named branches.

**Tech Stack:** Python 3.11, discord.py, Firestore, `unittest`, `importlib`, `pkgutil`

---

## File Structure

### Create

- `src/lifeguard/features/__init__.py` — exports registry and discovery helpers.
- `src/lifeguard/features/contracts.py` — shared manifest and adapter contracts.
- `src/lifeguard/features/discovery.py` — scans `lifeguard.modules` and imports manifests.
- `src/lifeguard/features/registry.py` — indexes manifests and resolves adapters.
- `src/lifeguard/features/bootstrap.py` — loads discovered cogs into the bot and stores the registry.
- `src/lifeguard/features/availability.py` — resolves visible feature entries from discovered modules plus guild history.
- `src/lifeguard/modules/time_impersonator/manifest.py` — Time Impersonator registration metadata.
- `src/lifeguard/modules/time_impersonator/config_adapter.py` — Time Impersonator shell adapter.
- `src/lifeguard/modules/time_impersonator/views/__init__.py` — exports config views for the module.
- `src/lifeguard/modules/time_impersonator/views/config_ui.py` — Time Impersonator config view moved out of the shared shell.
- `src/lifeguard/modules/voice_lobby/manifest.py` — Voice Lobby registration metadata.
- `src/lifeguard/modules/voice_lobby/config_adapter.py` — Voice Lobby shell adapter.
- `src/lifeguard/modules/voice_lobby/views/config_ui.py` — Voice Lobby config views moved out of the shared shell.
- `src/lifeguard/modules/content_review/manifest.py` — Content Review registration metadata.
- `src/lifeguard/modules/content_review/config_adapter.py` — Content Review shell adapter.
- `tests/features/test_registry.py` — discovery and registry tests.
- `tests/features/test_bootstrap.py` — bot bootstrap tests.
- `tests/features/test_availability.py` — availability and known-feature history tests.
- `tests/features/test_module_manifests.py` — discovered-module manifest coverage tests.
- `tests/cogs/test_config_shell_registry.py` — shared shell rendering and autocomplete tests.

### Modify

- `src/lifeguard/bot.py` — replace hardcoded module cog loading with registry bootstrap.
- `src/lifeguard/guild_settings.py` — persist historical feature keys alongside admin-role settings.
- `src/lifeguard/cogs/config_cog.py` — route through the registry instead of named module branches.
- `src/lifeguard/cogs/config_views.py` — keep only generic shell and general-settings views.
- `src/lifeguard/modules/time_impersonator/__init__.py` — keep package imports lightweight during manifest discovery.
- `src/lifeguard/modules/voice_lobby/__init__.py` — keep package imports lightweight during manifest discovery.
- `src/lifeguard/modules/content_review/__init__.py` — keep package imports lightweight during manifest discovery.
- `docs/Architecture.md` — document registry-backed startup and shell routing.
- `docs/ModuleDevelopment.md` — document manifest-based module registration.

### Delete After Migration

- `src/lifeguard/feature_interfaces.py` — remove once no imports remain.

### Notes

- Use `unittest` instead of `pytest` for the first pass because the repository has no existing test dependency or test runner wiring.
- Keep module business logic inside cogs and repos. The new adapters only translate generic shell actions into module-owned flows.
- Discovery should import dedicated `manifest.py` modules rather than relying on package-level `FEATURE_MANIFEST` re-exports.
- Keep `lifeguard.modules.<name>.__init__.py` files lightweight. Do not import cogs, repos, clients, or other heavy initialization work there during this migration.

### Task 1: Build the Feature Platform Core

**Files:**
- Create: `src/lifeguard/features/__init__.py`
- Create: `src/lifeguard/features/contracts.py`
- Create: `src/lifeguard/features/discovery.py`
- Create: `src/lifeguard/features/registry.py`
- Test: `tests/features/test_registry.py`

- [ ] **Step 1: Write the failing registry and discovery tests**

```python
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

    @patch("lifeguard.features.discovery.pkgutil.iter_modules")
    @patch("lifeguard.features.discovery.importlib.import_module")
    def test_discovery_imports_manifest_modules(self, import_module, iter_modules) -> None:
        package = types.SimpleNamespace(__path__=["modules"])
        manifest_module = types.SimpleNamespace(FEATURE_MANIFEST="manifest-object")

        def fake_import(name: str):
            if name == "lifeguard.modules":
                return package
            if name == "lifeguard.modules.alpha.manifest":
                return manifest_module
            if name == "lifeguard.modules.beta.manifest":
                raise ModuleNotFoundError(name)
            raise AssertionError(name)

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
```

- [ ] **Step 2: Run the test to verify the feature platform does not exist yet**

Run: `python -m unittest discover -s tests -p 'test_registry.py' -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'lifeguard.features'`

- [ ] **Step 3: Write the minimal contracts, discovery, and registry code**

```python
# src/lifeguard/features/contracts.py
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

import discord
from discord.ext import commands


class FeatureConfigAdapter(Protocol):
    async def show_menu(
        self,
        interaction: discord.Interaction,
        *,
        on_back_to_home: Callable[[discord.Interaction], Awaitable[None]],
    ) -> None: ...

    async def show_status(
        self,
        interaction: discord.Interaction,
        *,
        on_back_to_home: Callable[[discord.Interaction], Awaitable[None]],
    ) -> None: ...

    async def enable(
        self,
        interaction: discord.Interaction,
        *,
        on_back_to_home: Callable[[discord.Interaction], Awaitable[None]] | None = None,
        use_send: bool = False,
    ) -> None: ...

    async def disable(
        self,
        interaction: discord.Interaction,
        *,
        use_send: bool = False,
    ) -> None: ...

    async def show_setup(
        self,
        interaction: discord.Interaction,
        *,
        on_back_to_home: Callable[[discord.Interaction], Awaitable[None]],
        use_send: bool = False,
    ) -> None:
        raise NotImplementedError


@dataclass(frozen=True)
class FeatureManifest:
    feature_key: str
    display_name: str
    description: str
    emoji: str
    requires_setup: bool
    cog_name: str
    load_cog: Callable[[commands.Bot], commands.Cog]
    build_adapter: Callable[[commands.Bot], FeatureConfigAdapter]
```

```python
# src/lifeguard/features/registry.py
from __future__ import annotations

from dataclasses import dataclass

from discord.ext import commands

from lifeguard.features.contracts import FeatureConfigAdapter, FeatureManifest


class DuplicateFeatureKeyError(ValueError):
    pass


        settings: GuildSettings,
    ) -> list[FeatureEntry]:
class FeatureRegistry:
    _manifests: dict[str, FeatureManifest]

    @classmethod
    def from_manifests(cls, manifests: list[FeatureManifest]) -> "FeatureRegistry":
        indexed: dict[str, FeatureManifest] = {}
        for manifest in manifests:
            if manifest.feature_key in indexed:
            )
                raise DuplicateFeatureKeyError(manifest.feature_key)
            indexed[manifest.feature_key] = manifest
        return cls(indexed)

    def all_manifests(self) -> list[FeatureManifest]:
        return sorted(self._manifests.values(), key=lambda item: item.display_name)

    def get_manifest(self, feature_key: str) -> FeatureManifest | None:
        return self._manifests.get(feature_key)

        return sorted(entries.values(), key=lambda item: item.display_name)
    def build_adapter(

    - [ ] **Step 4: Run the availability tests again**

    Run: `python -m unittest discover -s tests -p 'test_availability.py' -v`

    Expected: PASS with `Ran 2 tests`
        self, bot: commands.Bot, feature_key: str
    - [ ] **Step 5: Commit the availability layer**
        manifest = self.get_manifest(feature_key)
        if manifest is None:
            return None
        return manifest.build_adapter(bot)
```

```python
# src/lifeguard/features/discovery.py
from __future__ import annotations

import importlib
import logging
import pkgutil

from lifeguard.features.contracts import FeatureManifest

LOGGER = logging.getLogger(__name__)


def discover_feature_manifests(package_name: str = "lifeguard.modules") -> list[FeatureManifest]:
    package = importlib.import_module(package_name)
    manifests: list[FeatureManifest] = []
    for _, module_name, is_pkg in pkgutil.iter_modules(package.__path__):
        if not is_pkg:
            continue
        try:
            module = importlib.import_module(f"{package_name}.{module_name}.manifest")
        except ModuleNotFoundError:
            LOGGER.warning("Skipping module without manifest.py: %s", module_name)
            continue
        manifest = getattr(module, "FEATURE_MANIFEST", None)
        if manifest is None:
            LOGGER.warning("Skipping manifest module without FEATURE_MANIFEST: %s", module.__name__)
            continue
        manifests.append(manifest)
    return manifests
```

```python
# src/lifeguard/features/__init__.py
from lifeguard.features.discovery import discover_feature_manifests
from lifeguard.features.registry import DuplicateFeatureKeyError, FeatureRegistry

__all__ = [
    "discover_feature_manifests",
    "DuplicateFeatureKeyError",
    "FeatureRegistry",
]
```

- [ ] **Step 4: Run the registry tests again**

Run: `python -m unittest discover -s tests -p 'test_registry.py' -v`

Expected: PASS with `Ran 2 tests`

- [ ] **Step 5: Commit the core feature platform**

```bash
git add tests/features/test_registry.py src/lifeguard/features/__init__.py src/lifeguard/features/contracts.py src/lifeguard/features/discovery.py src/lifeguard/features/registry.py
git commit -m "feat: add feature registry core"
```

### Task 2: Bootstrap Discovered Module Cogs in Bot Startup

**Files:**
- Create: `src/lifeguard/features/bootstrap.py`
- Modify: `src/lifeguard/bot.py`
- Test: `tests/features/test_bootstrap.py`

- [ ] **Step 1: Write the failing bootstrap test**

```python
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
```

- [ ] **Step 2: Run the bootstrap test to verify the helper is missing**

Run: `python -m unittest discover -s tests -p 'test_bootstrap.py' -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'lifeguard.features.bootstrap'`

- [ ] **Step 3: Implement registry bootstrap and replace hardcoded module loading in the bot**

```python
# src/lifeguard/features/bootstrap.py
from __future__ import annotations

from discord.ext import commands

from lifeguard.features.discovery import discover_feature_manifests
from lifeguard.features.registry import FeatureRegistry


async def register_module_features(
    bot: commands.Bot,
    *,
    package_name: str = "lifeguard.modules",
) -> FeatureRegistry:
    manifests = discover_feature_manifests(package_name)
    registry = FeatureRegistry.from_manifests(manifests)
    for manifest in registry.all_manifests():
        await bot.add_cog(manifest.load_cog(bot))
    return registry
```

```python
# src/lifeguard/bot.py key excerpts
from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from lifeguard.features.bootstrap import register_module_features

if TYPE_CHECKING:
    import aiohttp
    from google.cloud.firestore import Client as FirestoreClient

    from lifeguard.features.registry import FeatureRegistry


class LifeguardBot(commands.Bot):
    lifeguard_http_session: aiohttp.ClientSession
    lifeguard_firestore: FirestoreClient
    lifeguard_features: FeatureRegistry


def create_bot(config: Config) -> LifeguardBot:
    intents = discord.Intents.default()
    intents.message_content = True
    intents.voice_states = True
    bot = LifeguardBot(command_prefix=config.command_prefix, intents=intents)

    @bot.event
    async def setup_hook() -> None:
    import aiohttp

    from lifeguard.firestore_client import init_firestore

    session = aiohttp.ClientSession(headers={"Accept-Encoding": "gzip"})
    bot.lifeguard_http_session = session
    bot.lifeguard_firestore = init_firestore(config)
        await bot.add_cog(_load_core_cog(bot))
        bot.lifeguard_features = await register_module_features(bot)
        await bot.add_cog(_load_config_cog(bot))
```

After this edit, delete `_load_content_review_cog`, `_load_time_impersonator_cog`, and `_load_voice_lobby_cog` entirely instead of leaving dead code behind.

- [ ] **Step 4: Run the bootstrap test again**

Run: `python -m unittest discover -s tests -p 'test_bootstrap.py' -v`

Expected: PASS with `Ran 1 test`

- [ ] **Step 5: Commit the bot bootstrap change**

```bash
git add tests/features/test_bootstrap.py src/lifeguard/features/bootstrap.py src/lifeguard/bot.py
git commit -m "feat: bootstrap module cogs from discovered manifests"
```

### Task 3: Track Historical Features and Resolve Availability

**Files:**
- Create: `src/lifeguard/features/availability.py`
- Modify: `src/lifeguard/guild_settings.py`
- Test: `tests/features/test_availability.py`

- [ ] **Step 1: Write the failing availability tests**

```python
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
```

- [ ] **Step 2: Run the availability tests to verify guild history is not implemented yet**

Run: `python -m unittest discover -s tests -p 'test_availability.py' -v`

Expected: FAIL with `ImportError` for `lifeguard.features.availability` or `TypeError` for missing `known_feature_keys`

- [ ] **Step 3: Add availability entries and persist `known_feature_keys` in guild settings**

```python
# src/lifeguard/guild_settings.py dataclass excerpt
@dataclass
class GuildSettings:
    guild_id: int
    bot_admin_role_ids: list[int] = field(default_factory=list)
    known_feature_keys: list[str] = field(default_factory=list)

    def to_firestore(self) -> dict:
        return {
            "guild_id": self.guild_id,
            "bot_admin_role_ids": self.bot_admin_role_ids,
            "known_feature_keys": self.known_feature_keys,
        }

    @classmethod
    def from_firestore(cls, data: dict) -> "GuildSettings":
        return cls(
            guild_id=data["guild_id"],
            bot_admin_role_ids=data.get("bot_admin_role_ids", []),
            known_feature_keys=data.get("known_feature_keys", []),
        )


def remember_feature_key(settings: GuildSettings, feature_key: str) -> GuildSettings:
    if feature_key not in settings.known_feature_keys:
        settings.known_feature_keys.append(feature_key)
        settings.known_feature_keys.sort()
    return settings
```

```python
# src/lifeguard/features/availability.py
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
```

- [ ] **Step 4: Run the availability tests again**

Run: `python -m unittest discover -s tests -p 'test_availability.py' -v`

Expected: PASS with `Ran 2 tests`

- [ ] **Step 5: Commit the availability layer**

```bash
git add tests/features/test_availability.py src/lifeguard/features/availability.py src/lifeguard/guild_settings.py
git commit -m "feat: resolve feature availability from registry and guild history"
```

### Task 4: Migrate Time Impersonator and Voice Lobby to Manifests and Module-Owned Adapters

**Files:**
- Create: `src/lifeguard/modules/time_impersonator/manifest.py`
- Create: `src/lifeguard/modules/time_impersonator/config_adapter.py`
- Create: `src/lifeguard/modules/time_impersonator/views/__init__.py`
- Create: `src/lifeguard/modules/time_impersonator/views/config_ui.py`
- Create: `src/lifeguard/modules/voice_lobby/manifest.py`
- Create: `src/lifeguard/modules/voice_lobby/config_adapter.py`
- Create: `src/lifeguard/modules/voice_lobby/views/config_ui.py`
- Modify: `src/lifeguard/modules/time_impersonator/__init__.py`
- Modify: `src/lifeguard/modules/voice_lobby/__init__.py`
- Test: `tests/features/test_module_manifests.py`

- [ ] **Step 1: Write the failing manifest-coverage test**

```python
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
```

- [ ] **Step 2: Run the manifest test to verify modules are not exported yet**

Run: `python -m unittest discover -s tests -p 'test_module_manifests.py' -v`

Expected: FAIL because `discover_feature_manifests()` returns an empty list or skips existing modules.

- [ ] **Step 3: Add manifests and adapters for Time Impersonator and Voice Lobby**

```python
# src/lifeguard/modules/time_impersonator/manifest.py
from __future__ import annotations

from lifeguard.features.contracts import FeatureManifest
from lifeguard.modules.time_impersonator.cog import TimeImpersonatorCog
from lifeguard.modules.time_impersonator.config_adapter import TimeImpersonatorConfigAdapter


FEATURE_MANIFEST = FeatureManifest(
    feature_key="time_impersonator",
    display_name="Time Impersonator",
    description="Send messages with dynamic Discord timestamps",
    emoji="🕐",
    requires_setup=False,
    cog_name="TimeImpersonatorCog",
    load_cog=lambda bot: TimeImpersonatorCog(bot),
    build_adapter=lambda bot: TimeImpersonatorConfigAdapter(bot),
)
```

```python
# src/lifeguard/modules/time_impersonator/config_adapter.py
from __future__ import annotations

from typing import cast

from discord.ext import commands

from lifeguard.modules.time_impersonator.cog import TimeImpersonatorCog
from lifeguard.modules.time_impersonator.views.config_ui import TimeImpersonatorConfigView


class TimeImpersonatorConfigAdapter:
    def __init__(self, bot: commands.Bot) -> None:
        self._cog = cast(TimeImpersonatorCog, bot.get_cog("TimeImpersonatorCog"))

    async def show_menu(self, interaction, *, on_back_to_home) -> None:
        await self._cog.show_config_status(
            interaction,
            view=TimeImpersonatorConfigView(self, on_back_to_home=on_back_to_home),
        )

    async def show_status(self, interaction, *, on_back_to_home) -> None:
        await self.show_menu(interaction, on_back_to_home=on_back_to_home)

    async def enable(self, interaction, *, on_back_to_home=None, use_send: bool = False) -> None:
        await self._cog.enable_feature(interaction, use_send=use_send)

    async def disable(self, interaction, *, use_send: bool = False) -> None:
        await self._cog.disable_feature(interaction, use_send=use_send)
```

```python
# src/lifeguard/modules/voice_lobby/manifest.py
from __future__ import annotations

from lifeguard.features.contracts import FeatureManifest
from lifeguard.modules.voice_lobby.cog import VoiceLobbyCog
from lifeguard.modules.voice_lobby.config_adapter import VoiceLobbyConfigAdapter


FEATURE_MANIFEST = FeatureManifest(
    feature_key="voice_lobby",
    display_name="Voice Lobby",
    description="Temporary voice lobbies created from an entry channel",
    emoji="🎧",
    requires_setup=False,
    cog_name="VoiceLobbyCog",
    load_cog=lambda bot: VoiceLobbyCog(bot),
    build_adapter=lambda bot: VoiceLobbyConfigAdapter(bot),
)
```

```python
# src/lifeguard/modules/voice_lobby/config_adapter.py
from __future__ import annotations

from typing import cast

from discord.ext import commands

from lifeguard.modules.voice_lobby.cog import VoiceLobbyCog
from lifeguard.modules.voice_lobby.views.config_ui import VoiceLobbyConfigView


class VoiceLobbyConfigAdapter:
    def __init__(self, bot: commands.Bot) -> None:
        self._cog = cast(VoiceLobbyCog, bot.get_cog("VoiceLobbyCog"))

    async def show_menu(self, interaction, *, on_back_to_home) -> None:
        await self._cog.show_config_status(
            interaction,
            view=VoiceLobbyConfigView(self, on_back_to_home=on_back_to_home),
        )

    async def show_status(self, interaction, *, on_back_to_home) -> None:
        await self.show_menu(interaction, on_back_to_home=on_back_to_home)

    async def enable(self, interaction, *, on_back_to_home=None, use_send: bool = False) -> None:
        await self._cog.enable_feature(interaction, use_send=use_send)

    async def disable(self, interaction, *, use_send: bool = False) -> None:
        await self._cog.disable_feature(interaction, use_send=use_send)
```

Move the existing `TimeImpersonatorConfigView` class out of `src/lifeguard/cogs/config_views.py` into `src/lifeguard/modules/time_impersonator/views/config_ui.py`, and move the existing Voice Lobby view classes out of `src/lifeguard/cogs/config_views.py` into `src/lifeguard/modules/voice_lobby/views/config_ui.py` with the constructor dependency changed from `ConfigCog` to the new adapter classes.

Keep the module `__init__.py` files lightweight. Do not export `FEATURE_MANIFEST` from package `__init__.py`; discovery should import `manifest.py` directly.

```python
from lifeguard.modules.time_impersonator.models import UserTimezone

__all__ = ["UserTimezone"]
```

- [ ] **Step 4: Run the manifest test again**

Run: `python -m unittest discover -s tests -p 'test_module_manifests.py' -v`

Expected: FAIL only because `content_review` still does not export a manifest.

- [ ] **Step 5: Commit the first module migration**

```bash
git add tests/features/test_module_manifests.py src/lifeguard/modules/time_impersonator/__init__.py src/lifeguard/modules/time_impersonator/manifest.py src/lifeguard/modules/time_impersonator/config_adapter.py src/lifeguard/modules/time_impersonator/views/__init__.py src/lifeguard/modules/time_impersonator/views/config_ui.py src/lifeguard/modules/voice_lobby/__init__.py src/lifeguard/modules/voice_lobby/manifest.py src/lifeguard/modules/voice_lobby/config_adapter.py src/lifeguard/modules/voice_lobby/views/config_ui.py
git commit -m "feat: register time and voice modules through manifests"
```

### Task 5: Migrate Content Review and Refactor the Shared Config Shell to the Registry

**Files:**
- Create: `src/lifeguard/modules/content_review/manifest.py`
- Create: `src/lifeguard/modules/content_review/config_adapter.py`
- Modify: `src/lifeguard/modules/content_review/__init__.py`
- Modify: `src/lifeguard/modules/content_review/cog.py`
- Modify: `src/lifeguard/modules/content_review/views/config_ui.py`
- Modify: `src/lifeguard/cogs/config_cog.py`
- Modify: `src/lifeguard/cogs/config_views.py`
- Delete: `src/lifeguard/feature_interfaces.py`
- Test: `tests/cogs/test_config_shell_registry.py`

- [ ] **Step 1: Write the failing shell-rendering and autocomplete tests**

```python
import unittest

from lifeguard.features.availability import FeatureEntry


class ConfigShellViewTests(unittest.TestCase):
    def test_top_level_view_builds_select_options_from_feature_entries(self) -> None:
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

        self.assertEqual([option.value for option in select.options], ["time_impersonator", "voice_lobby"])

    def test_autocomplete_filters_registry_entries(self) -> None:
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
```

- [ ] **Step 2: Run the shell tests to verify the old fixed-button shell is still active**

Run: `python -m unittest discover -s tests -p 'test_config_shell_registry.py' -v`

Expected: FAIL because `ConfigHomeView` and `build_feature_autocomplete_choices()` do not exist.

- [ ] **Step 3: Add the Content Review manifest and replace hardcoded shell routing with registry dispatch**

```python
# src/lifeguard/modules/content_review/manifest.py
from __future__ import annotations

from lifeguard.features.contracts import FeatureManifest
from lifeguard.modules.content_review.cog import ContentReviewCog
from lifeguard.modules.content_review.config_adapter import ContentReviewConfigAdapter


FEATURE_MANIFEST = FeatureManifest(
    feature_key="content_review",
    display_name="Content Review",
    description="Review system with tickets, scoring, and leaderboards",
    emoji="📝",
    requires_setup=True,
    cog_name="ContentReviewCog",
    load_cog=lambda bot: ContentReviewCog(bot),
    build_adapter=lambda bot: ContentReviewConfigAdapter(bot),
)
```

```python
# src/lifeguard/modules/content_review/config_adapter.py
from __future__ import annotations

from typing import cast

from discord.ext import commands

from lifeguard.modules.content_review.cog import ContentReviewCog


class ContentReviewConfigAdapter:
    def __init__(self, bot: commands.Bot) -> None:
        self._cog = cast(ContentReviewCog, bot.get_cog("ContentReviewCog"))

    async def show_menu(self, interaction, *, on_back_to_home) -> None:
        await self._cog.show_config_menu(
            interaction,
            disabled_view=None,
            on_back_to_home=on_back_to_home,
        )

    async def show_status(self, interaction, *, on_back_to_home) -> None:
        await self.show_menu(interaction, on_back_to_home=on_back_to_home)

    async def show_setup(self, interaction, *, on_back_to_home, use_send: bool = False) -> None:
        await self._cog.show_setup(
            interaction,
            on_back_to_home=on_back_to_home,
            use_send=use_send,
        )

    async def enable(self, interaction, *, on_back_to_home=None, use_send: bool = False) -> None:
        if on_back_to_home is None:
            raise RuntimeError("Content Review setup requires an on_back_to_home callback")
        await self.show_setup(interaction, on_back_to_home=on_back_to_home, use_send=use_send)

    async def disable(self, interaction, *, use_send: bool = False) -> None:
        await self._cog.disable_feature(interaction, use_send=use_send)
```

```python
# src/lifeguard/modules/content_review/cog.py setup excerpt
async def show_setup(
    self,
    interaction: discord.Interaction,
    *,
    on_back_to_home: Callable[[discord.Interaction], Awaitable[None]] | None = None,
    use_send: bool = False,
) -> None:
    view = ContentReviewSetupView(self, on_back_to_home=on_back_to_home)
    embed = discord.Embed(
        title="📝 Content Review Setup",
        description=(
            "Select the **ticket category** where review channels will be created.\n\n"
            "The submit button will be posted in the current channel."
        ),
        color=discord.Color.blue(),
    )
    if use_send:
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    else:
        await interaction.response.edit_message(content=None, embed=embed, view=view)
```

```python
# src/lifeguard/modules/content_review/views/config_ui.py setup excerpt
class ContentReviewSetupView(discord.ui.View):
    def __init__(self, cog: "ContentReviewCog", on_back_to_home=None) -> None:
        super().__init__(timeout=120)
        self.cog = cog
        self._on_back_to_home = on_back_to_home

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️")
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._on_back_to_home is None:
            await interaction.response.edit_message(content="Setup cancelled.", embed=None, view=None)
            return
        await self._on_back_to_home(interaction)
```

```python
# src/lifeguard/cogs/config_cog.py key excerpts
from lifeguard.features.availability import FeatureEntry, resolve_feature_entries
from lifeguard.features.registry import FeatureRegistry
from lifeguard.guild_settings import (
    get_guild_settings,
    get_or_create_guild_settings,
    remember_feature_key,
    save_guild_settings,
)


def build_feature_autocomplete_choices(
    feature_entries: list[FeatureEntry], current: str
) -> list[app_commands.Choice[str]]:
    current_lower = current.lower()
    matches = []
    for entry in feature_entries:
        if entry.status != "available":
            continue
        haystacks = (entry.feature_key.lower(), entry.display_name.lower())
        if current_lower and not any(current_lower in haystack for haystack in haystacks):
            continue
        matches.append(
            app_commands.Choice(
                name=f"{entry.display_name} - {entry.description}",
                value=entry.feature_key,
            )
        )
    return matches[:25]


class ConfigCog(commands.Cog):
    @property
    def feature_registry(self) -> FeatureRegistry:
        return self.bot.lifeguard_features

    def _feature_entries(self, guild_id: int) -> list[FeatureEntry]:
        settings = get_or_create_guild_settings(self.firestore, guild_id)
        return resolve_feature_entries(self.feature_registry, settings)

    def _remember_feature(self, guild_id: int, feature_key: str) -> None:
        settings = get_or_create_guild_settings(self.firestore, guild_id)
        remember_feature_key(settings, feature_key)
        save_guild_settings(self.firestore, settings)

    async def _dispatch_feature_menu(self, interaction: discord.Interaction, feature_key: str) -> None:
        manifest = self.feature_registry.get_manifest(feature_key)
        if manifest is None:
            await interaction.response.edit_message(
                content=f"{feature_key.replace('_', ' ').title()} is not currently installed.",
                embed=None,
                view=None,
            )
            return
        self._remember_feature(interaction.guild.id, feature_key)
        adapter = self.feature_registry.build_adapter(self.bot, feature_key)
        await adapter.show_menu(interaction, on_back_to_home=self._show_config_home)

    async def enable_feature_command(self, interaction: discord.Interaction, feature: str) -> None:
        manifest = self.feature_registry.get_manifest(feature)
        adapter = self.feature_registry.build_adapter(self.bot, feature)
        if manifest is None or adapter is None:
            await interaction.response.send_message(
                f"Unknown feature: `{feature}`. Use autocomplete to select a valid feature.",
                ephemeral=True,
            )
            return
        self._remember_feature(interaction.guild.id, feature)
        if manifest.requires_setup:
            await adapter.show_setup(
                interaction,
                on_back_to_home=self._show_config_home,
                use_send=True,
            )
            return
        await adapter.enable(
            interaction,
            on_back_to_home=self._show_config_home,
            use_send=True,
        )
```

```python
# src/lifeguard/cogs/config_views.py key excerpts
class ConfigFeatureSelect(discord.ui.Select):
    def __init__(self, cog: "ConfigCog", feature_entries: list[FeatureEntry]) -> None:
        options = [
            discord.SelectOption(
                label=entry.display_name,
                value=entry.feature_key,
                description=entry.description[:100],
                emoji=entry.emoji,
            )
            for entry in feature_entries
        ]
        super().__init__(placeholder="Choose a feature...", options=options)
        self.cog = cog

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.cog._dispatch_feature_menu(interaction, self.values[0])


class ConfigHomeView(discord.ui.View):
    def __init__(self, cog: "ConfigCog", feature_entries: list[FeatureEntry]) -> None:
        super().__init__(timeout=120)
        self.cog = cog
        if feature_entries:
            self.add_item(ConfigFeatureSelect(cog, feature_entries))
```

After the registry-backed shell works, delete `src/lifeguard/feature_interfaces.py` and remove all imports of `TimeImpersonatorConfigView`, `VoiceLobbyConfigView`, `SupportsConfigToggle`, `SupportsContentReviewConfig`, and `SupportsVoiceLobbyConfig` from the shared shell.

- [ ] **Step 4: Search for residual feature-interface references and remove them**

Run: `rg "SupportsConfigToggle|SupportsContentReviewConfig|SupportsVoiceLobbyConfig|feature_interfaces" src/lifeguard`

Expected before delete: matches in `src/lifeguard/cogs/config_cog.py` and `src/lifeguard/feature_interfaces.py`

Expected after edit: no matches

- [ ] **Step 5: Run the shell and manifest tests again**

Run: `python -m unittest discover -s tests -p 'test_config_shell_registry.py' -v`

Expected: PASS with `Ran 2 tests`

Run: `python -m unittest discover -s tests -p 'test_module_manifests.py' -v`

Expected: PASS with `Ran 1 test`

- [ ] **Step 6: Commit the registry-backed config shell**

```bash
git rm src/lifeguard/feature_interfaces.py
git add tests/cogs/test_config_shell_registry.py src/lifeguard/modules/content_review/__init__.py src/lifeguard/modules/content_review/manifest.py src/lifeguard/modules/content_review/config_adapter.py src/lifeguard/cogs/config_cog.py src/lifeguard/cogs/config_views.py
git commit -m "feat: route shared config shell through feature registry"
```

### Task 6: Update Documentation and Run Full Verification

**Files:**
- Modify: `docs/Architecture.md`
- Modify: `docs/ModuleDevelopment.md`
- Test: `tests/features/test_registry.py`
- Test: `tests/features/test_bootstrap.py`
- Test: `tests/features/test_availability.py`
- Test: `tests/features/test_module_manifests.py`
- Test: `tests/cogs/test_config_shell_registry.py`

- [ ] **Step 1: Update architecture and module-development docs to match the registry model**

```markdown
## Bot Factory (`bot.py`)
The bot discovers feature manifests under `lifeguard.modules`, builds a `FeatureRegistry`, stores it on `bot.lifeguard_features`, and loads feature cogs from manifest factories during `setup_hook`.

## Adding a Module
1. Create `manifest.py` exporting `FEATURE_MANIFEST`.
2. Implement a module-owned config adapter that satisfies `FeatureConfigAdapter`.
3. Keep package `__init__.py` lightweight and avoid importing cogs or repositories there.
4. Confirm `python -m unittest discover -s tests -p 'test_module_manifests.py' -v` still passes.
```

- [ ] **Step 2: Run the full unit test suite**

Run: `python -m unittest discover -s tests -p 'test_*.py' -v`

Expected: PASS with all registry, bootstrap, availability, manifest, and shell tests green.

- [ ] **Step 3: Run a syntax validation pass over the bot package**

Run: `python -m compileall src/lifeguard`

Expected: PASS with no syntax errors reported.

- [ ] **Step 4: Run the bot once in test mode to verify startup still works with discovered modules**

Run: `python -m lifeguard`

Environment: `BOT_ENV=test`

Expected: Startup logs show module discovery, registry population, and command sync without import errors.

- [ ] **Step 5: Commit the docs and final verification changes**

```bash
git add docs/Architecture.md docs/ModuleDevelopment.md tests/features/test_registry.py tests/features/test_bootstrap.py tests/features/test_availability.py tests/features/test_module_manifests.py tests/cogs/test_config_shell_registry.py src/lifeguard
git commit -m "docs: document registry-backed module configuration"
```

## Self-Review

- Spec coverage: this plan covers discovery, registry creation, bot startup, module migration, shared shell refactor, historical feature handling, documentation, and validation.
- Placeholder scan: no `TBD`, `TODO`, or “implement later” markers remain.
- Type consistency: the plan uses `FeatureManifest`, `FeatureRegistry`, `FeatureConfigAdapter`, and `FeatureEntry` consistently from introduction through shell migration.