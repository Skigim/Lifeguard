# Post-Spec Cleanup Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean up transitional surfaces left behind after the module registry and generic forms engine landed, while keeping the shipped behavior and migration safety intact.

**Architecture:** Treat the registry and forms work as complete infrastructure. This pass does not add new feature behavior. It narrows compatibility boundaries to the smallest necessary surface, adds regression tests around historical feature preservation, and reconciles documentation with the modules that actually ship on main.

**Tech Stack:** Python 3.13, discord.py, Firestore, `unittest`, Markdown docs

---

## Audit Summary

- The registry-backed config shell is implemented and covered by targeted tests.
- The shared forms engine is implemented and content review is migrated onto it.
- The main remaining debt is transitional cleanup, not missing core behavior.
- The cleanup targets found during audit are:
  - internal `content_review` code still uses `ReviewCategory`, `SubmissionField`, and `review_categories` compatibility surfaces
  - historical feature preservation is implemented, but the config-cog backfill path is not directly tested
  - repo docs still mention Albion as if it ships on main, while discovery only finds `content_review`, `time_impersonator`, and `voice_lobby`

## File Structure

### Create

- `tests/cogs/test_config_feature_history.py` — focused regression tests for remembered feature history and config backfill.

### Modify

- `src/lifeguard/modules/content_review/cog.py` — replace internal compatibility aliases with shared forms types.
- `src/lifeguard/modules/content_review/embeds.py` — render score categories from `form_categories` directly.
- `src/lifeguard/modules/content_review/config.py` — keep Firestore legacy reads but reduce the runtime compatibility surface to migration-only helpers.
- `src/lifeguard/modules/content_review/__init__.py` — stop exporting compatibility aliases that are no longer used internally.
- `tests/modules/content_review/test_config_migration.py` — keep legacy Firestore read/write coverage after the cleanup.
- `tests/modules/content_review/test_review_flow_compat.py` — pin the forms-based flow after internal alias removal.
- `README.md` — remove or relocate shipped-feature claims that do not match main.
- `.github/CONTRIBUTING.md` — align module examples with modules that actually exist on main.
- `docs/FeatureCatalogue.md` — align supported feature inventory with discovered manifests.
- `docs/PlannedFeatures.md` — move any future Albion mention here if it should remain documented.

### Notes

- Keep legacy Firestore deserialization of `review_categories` until an explicit data migration removes the need.
- Do not change user-visible review behavior in this pass.
- Avoid broad refactors in the registry layer unless a new regression test proves the need.
- If Albion is intentionally planned but not shipped, document it as planned; do not leave it described as active functionality.

## Task 1: Add Regression Coverage For Historical Feature Preservation

**Files:**
- Create: `tests/cogs/test_config_feature_history.py`
- Modify: `tests/cogs/test_config_shell_registry.py`
- Modify: `src/lifeguard/cogs/config_cog.py` (only if the new test exposes a real defect)

- [ ] **Step 1: Write the failing backfill and history tests**

```python
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
                    "guild_settings": {"42": FakeGuildSettingsDoc(True, {"guild_id": 42})},
                    "content_review_configs": {"42": FakeConfigDoc(True, {"guild_id": 42})},
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
        settings_doc = bot.lifeguard_firestore.collection("guild_settings").document("42")
        self.assertEqual(settings_doc.to_dict()["known_feature_keys"], ["content_review"])
```

- [ ] **Step 2: Run the focused config-shell tests to confirm the new case fails first**

Run: `c:/Users/dwigh/OneDrive/Documents/Projects/Lifeguard/.venv/Scripts/python.exe -m unittest tests.cogs.test_config_shell_registry tests.cogs.test_config_feature_history -v`

Expected: FAIL because the new test file does not exist yet.

- [ ] **Step 3: Add the regression test with the smallest fake Firestore surface needed**

```python
# tests/cogs/test_config_feature_history.py
import unittest


class ConfigFeatureHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_backfill_remembers_feature_when_module_config_exists(self) -> None:
        ...
```

Keep the fakes local to the test file. Do not introduce new production helpers only for tests.

- [ ] **Step 4: Run the focused config-shell tests again**

Run: `c:/Users/dwigh/OneDrive/Documents/Projects/Lifeguard/.venv/Scripts/python.exe -m unittest tests.cogs.test_config_shell_registry tests.cogs.test_config_feature_history -v`

Expected: PASS with both the existing shell tests and the new history test green.

- [ ] **Step 5: Commit the regression coverage**

```bash
git add tests/cogs/test_config_shell_registry.py tests/cogs/test_config_feature_history.py
git commit -m "test: cover feature history backfill"
```

## Task 2: Remove Internal Content Review Compatibility Aliases

**Files:**
- Modify: `src/lifeguard/modules/content_review/cog.py`
- Modify: `src/lifeguard/modules/content_review/embeds.py`
- Modify: `src/lifeguard/modules/content_review/config.py`
- Modify: `src/lifeguard/modules/content_review/__init__.py`
- Modify: `tests/modules/content_review/test_config_migration.py`
- Modify: `tests/modules/content_review/test_review_flow_compat.py`

- [ ] **Step 1: Write the failing cleanup test that pins the forms-native runtime surface**

```python
import unittest

from lifeguard.features.forms.schema import FormCategory, FormField, ScoreOptions
from lifeguard.modules.content_review.config import ContentReviewConfig


class ContentReviewRuntimeSurfaceTests(unittest.TestCase):
    def test_default_config_uses_forms_native_runtime_lists(self) -> None:
        config = ContentReviewConfig.default(123)

        self.assertIsInstance(config.submission_fields[0], FormField)
        self.assertIsInstance(config.form_categories[0], FormCategory)
        self.assertEqual(config.form_categories[0].response_kind, "score")
        self.assertEqual(
            config.form_categories[0].options,
            ScoreOptions(min_value=1, max_value=5, allow_note=True),
        )
```

- [ ] **Step 2: Run the focused content review tests to verify the new cleanup case starts red**

Run: `c:/Users/dwigh/OneDrive/Documents/Projects/Lifeguard/.venv/Scripts/python.exe -m unittest tests.modules.content_review.test_config_migration tests.modules.content_review.test_review_flow_compat -v`

Expected: FAIL until the new test is added and the internal call sites stop relying on compatibility-only aliases.

- [ ] **Step 3: Replace internal alias usage in the content review runtime**

```python
# src/lifeguard/modules/content_review/cog.py
from lifeguard.features.forms.schema import FormCategory, FormField, ScoreOptions
from lifeguard.modules.content_review.config import ContentReviewConfig

...

if config.form_categories:
    category_ids = ", ".join(category.id for category in config.form_categories)

new_field = FormField(
    id=field_id,
    label=label,
    field_type=field_type,
    required=required,
    placeholder=placeholder,
)

new_category = FormCategory(
    id=category_id,
    name=name,
    description=description,
    response_kind="score",
    required=required,
    options=ScoreOptions(
        min_value=min_score,
        max_value=max_score,
        allow_note=allow_notes,
    ),
)
```

```python
# src/lifeguard/modules/content_review/embeds.py
for category in config.form_categories:
    score_options = cast(ScoreOptions, category.options)
    ...
```

```python
# src/lifeguard/modules/content_review/__init__.py
from lifeguard.features.forms.schema import FormCategory, FormField
from lifeguard.modules.content_review.config import ContentReviewConfig

__all__ = [
    "ContentReviewConfig",
    "FormCategory",
    "FormField",
    ...
]
```

Keep Firestore legacy support in `config.py`, but stop treating `ReviewCategory` and `SubmissionField` as normal runtime types in module internals.

- [ ] **Step 4: Run the focused content review tests again**

Run: `c:/Users/dwigh/OneDrive/Documents/Projects/Lifeguard/.venv/Scripts/python.exe -m unittest tests.modules.content_review.test_config_migration tests.modules.content_review.test_review_flow_compat tests.modules.content_review.test_forms_translation -v`

Expected: PASS with migration coverage intact and the forms-based runtime still green.

- [ ] **Step 5: Commit the internal cleanup**

```bash
git add src/lifeguard/modules/content_review/cog.py src/lifeguard/modules/content_review/embeds.py src/lifeguard/modules/content_review/config.py src/lifeguard/modules/content_review/__init__.py tests/modules/content_review/test_config_migration.py tests/modules/content_review/test_review_flow_compat.py
git commit -m "refactor: remove internal content review compatibility aliases"
```

## Task 3: Reconcile Shipped Documentation With Actual Main-Branch Modules

**Files:**
- Modify: `README.md`
- Modify: `.github/CONTRIBUTING.md`
- Modify: `docs/FeatureCatalogue.md`
- Modify: `docs/PlannedFeatures.md`

- [ ] **Step 1: Write the failing documentation inventory check as a manual grep gate**

Run: `rg -n "Albion Commands|albion-price|modules/        # Feature modules \(albion, content_review, etc\.\)" README.md .github/CONTRIBUTING.md docs`

Expected: MATCHES that show Albion is still described as shipped.

- [ ] **Step 2: Update the docs so they describe main accurately**

```md
## Supported Features

- Content Review
- Time Impersonator
- Voice Lobby
```

```md
## Planned Features

- Albion integration
```

Keep the docs consistent with the discovered manifests on main. Do not leave README examples that imply working slash commands for a module that is not shipped.

- [ ] **Step 3: Re-run the grep gate to confirm the stale shipped references are gone**

Run: `rg -n "Albion Commands|albion-price|modules/        # Feature modules \(albion, content_review, etc\.\)" README.md .github/CONTRIBUTING.md docs`

Expected: no matches for shipped-feature wording; only planned-feature references remain where intentional.

- [ ] **Step 4: Run the full post-cleanup verification slice**

Run: `c:/Users/dwigh/OneDrive/Documents/Projects/Lifeguard/.venv/Scripts/python.exe -m unittest tests.features.test_registry tests.features.test_bootstrap tests.features.test_availability tests.features.test_module_manifests tests.cogs.test_config_shell_registry tests.cogs.test_config_feature_history tests.features.forms.test_schema tests.features.forms.test_models tests.features.forms.test_repo tests.features.forms.test_wizard tests.modules.content_review.test_config_migration tests.modules.content_review.test_forms_translation tests.modules.content_review.test_review_flow_compat -v`

Expected: PASS with the registry/forms regression suite green.

- [ ] **Step 5: Commit the docs cleanup**

```bash
git add README.md .github/CONTRIBUTING.md docs/FeatureCatalogue.md docs/PlannedFeatures.md
git commit -m "docs: align shipped modules with main"
```

## Self-Review Checklist

- Spec-follow-up scope stays narrow: cleanup only, no new product behavior.
- Legacy Firestore compatibility remains covered by tests.
- Registry history preservation is explicitly tested, not just inferred.
- Main-branch docs match discovered modules and tested functionality.