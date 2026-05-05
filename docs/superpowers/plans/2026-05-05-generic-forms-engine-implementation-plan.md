# Generic Forms Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace review-specific category and wizard primitives in `content_review` with a shared generic forms engine that supports multiple response kinds, persisted generic response sessions, and a safe migration from `review_categories` to `form_categories` without breaking the current review flow.

**Architecture:** Add a shared `lifeguard.features.forms` package that owns generic form fields, category schema, response/session models, validation, a generic category wizard, and Firestore persistence helpers. Refactor `content_review` to use that package through a translation layer so existing review publishing, embeds, and profile logic stay feature-local while generic response capture and persistence move into shared infrastructure.

**Tech Stack:** Python 3.11, discord.py, Firestore, `unittest`

---

## File Structure

### Create

- `src/lifeguard/features/forms/__init__.py` — exports generic forms primitives.
- `src/lifeguard/features/forms/schema.py` — `FormField`, `FormCategory`, response-kind enums, and typed option models.
- `src/lifeguard/features/forms/models.py` — generic runtime and persisted response/session models.
- `src/lifeguard/features/forms/repo.py` — Firestore CRUD for generic form response sessions.
- `src/lifeguard/features/forms/wizard.py` — generic category wizard view plus pure validation and summary helpers.
- `src/lifeguard/features/forms/submission_modal.py` — generic intake modal moved out of `content_review`.
- `src/lifeguard/modules/content_review/forms_translation.py` — translation from generic forms config and sessions to review-specific outputs.
- `tests/features/forms/test_schema.py` — round-trip tests for schema and response-kind options.
- `tests/features/forms/test_models.py` — round-trip tests for generic response and session models.
- `tests/features/forms/test_repo.py` — shared forms repo tests.
- `tests/features/forms/test_wizard.py` — generic validation and wizard behavior tests.
- `tests/modules/content_review/test_config_migration.py` — config rename and legacy read tests.
- `tests/modules/content_review/test_forms_translation.py` — translation-layer tests.
- `tests/modules/content_review/test_review_flow_compat.py` — content review compatibility tests.

### Modify

- `src/lifeguard/modules/content_review/config.py` — replace `SubmissionField` and `ReviewCategory` usage with shared forms schema and migrate `review_categories` to `form_categories`.
- `src/lifeguard/modules/content_review/__init__.py` — re-export `FormField` and `FormCategory` during migration so existing package-level imports do not break immediately.
- `src/lifeguard/modules/content_review/cog.py` — replace review-specific wizard and submission modal usage with shared forms engine.
- `src/lifeguard/modules/content_review/models.py` — keep review-specific models but add helpers that consume translated generic session data where needed.
- `src/lifeguard/modules/content_review/repo.py` — keep review-specific persistence intact while coordinating config migration and any session linkage needed by content review.
- `src/lifeguard/modules/content_review/views/config_ui.py` — use `FormCategory` and shared field/category schema instead of review-specific types.
- `src/lifeguard/modules/content_review/views/submission_modal.py` — delete after callers are migrated to the shared modal.
- `src/lifeguard/modules/content_review/views/review_wizard.py` — delete after callers are migrated to the shared wizard.
- `docs/ModuleDevelopment.md` — document the shared forms package as the default path for configurable forms.
- `docs/Architecture.md` — document the new shared forms boundary and content review translation layer.

### Notes

- Keep `content_review` publish logic local. The shared forms package captures and stores generic responses but does not know how a feature uses them.
- Prefer small pure helper functions in `wizard.py` for validation and summary rendering so tests do not need to simulate Discord interactions for every rule.
- During migration, read both `form_categories` and legacy `review_categories`, but only write `form_categories` after the new config path is active.
- Preserve current review-facing output semantics even if the underlying wizard draft/session types change.

## Task 1: Build the Shared Forms Schema

**Files:**
- Create: `src/lifeguard/features/forms/__init__.py`
- Create: `src/lifeguard/features/forms/schema.py`
- Test: `tests/features/forms/test_schema.py`

- [ ] **Step 1: Write the failing schema tests**

```python
import unittest


class FormSchemaTests(unittest.TestCase):
    def test_form_category_round_trips_score_options(self) -> None:
        from lifeguard.features.forms.schema import FormCategory, ScoreOptions

        category = FormCategory(
            id="overall",
            name="Overall",
            description="Rate overall quality",
            response_kind="score",
            required=True,
            options=ScoreOptions(min_value=1, max_value=5, allow_note=True),
        )

        restored = FormCategory.from_firestore(category.to_firestore())

        self.assertEqual(restored.response_kind, "score")
        self.assertEqual(restored.options.min_value, 1)
        self.assertEqual(restored.options.max_value, 5)
        self.assertTrue(restored.options.allow_note)

    def test_select_category_round_trips_choices(self) -> None:
        from lifeguard.features.forms.schema import (
            ChoiceOption,
            FormCategory,
            SelectOptions,
        )

        category = FormCategory(
            id="status",
            name="Status",
            response_kind="single_select",
            options=SelectOptions(
                choices=[
                    ChoiceOption(id="ready", label="Ready"),
                    ChoiceOption(id="blocked", label="Blocked"),
                ],
                min_selected=1,
                max_selected=1,
            ),
        )

        restored = FormCategory.from_firestore(category.to_firestore())

        self.assertEqual(restored.options.choices[0].id, "ready")
        self.assertEqual(restored.options.max_selected, 1)

    def test_unknown_response_kind_is_rejected(self) -> None:
        from lifeguard.features.forms.schema import InvalidFormSchemaError, FormCategory

        with self.assertRaises(InvalidFormSchemaError):
            FormCategory.from_firestore(
                {
                    "id": "bad",
                    "name": "Bad",
                    "response_kind": "unsupported",
                    "options": {},
                }
            )
```

- [ ] **Step 2: Run the schema tests to confirm the package does not exist yet**

Run: `python -m unittest discover -s tests/features/forms -p 'test_schema.py' -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'lifeguard.features.forms'`

- [ ] **Step 3: Implement the shared schema types**

```python
# src/lifeguard/features/forms/schema.py
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

from lifeguard.utils import drop_none

ResponseKind = Literal[
    "score",
    "note",
    "text",
    "boolean",
    "single_select",
    "multi_select",
]


class InvalidFormSchemaError(ValueError):
    """Raised when a form field or category has an invalid schema."""


@dataclass(frozen=True)
class ChoiceOption:
    id: str
    label: str

    @classmethod
    def from_firestore(cls, data: dict) -> "ChoiceOption":
        return cls(id=data["id"], label=data["label"])


@dataclass(frozen=True)
class ScoreOptions:
    min_value: int = 1
    max_value: int = 5
    allow_note: bool = True


@dataclass(frozen=True)
class SelectOptions:
    choices: list[ChoiceOption] = field(default_factory=list)
    min_selected: int = 1
    max_selected: int = 1


@dataclass(frozen=True)
class TextOptions:
    style: Literal["short", "paragraph"] = "short"
    placeholder: str = ""
    validation_regex: str = ""


@dataclass(frozen=True)
class BooleanOptions:
    true_label: str = "Yes"
    false_label: str = "No"


@dataclass(frozen=True)
class NoteOptions:
    placeholder: str = ""
    required_reference: bool = False


@dataclass(frozen=True)
class FormField:
    id: str
    label: str
    field_type: Literal["short_text", "paragraph", "url"] = "short_text"
    required: bool = True
    placeholder: str = ""
    validation_regex: str = ""

    def to_firestore(self) -> dict:
        return drop_none(asdict(self))

    @classmethod
    def from_firestore(cls, data: dict) -> "FormField":
        return cls(
            id=data["id"],
            label=data["label"],
            field_type=data.get("field_type", "short_text"),
            required=data.get("required", True),
            placeholder=data.get("placeholder", ""),
            validation_regex=data.get("validation_regex", ""),
        )


@dataclass(frozen=True)
class FormCategory:
    id: str
    name: str
    description: str = ""
    response_kind: ResponseKind = "text"
    required: bool = True
    options: ScoreOptions | SelectOptions | TextOptions | BooleanOptions | NoteOptions = field(
        default_factory=TextOptions
    )

    def to_firestore(self) -> dict:
        payload = drop_none(asdict(self))
        payload["options"] = _options_to_firestore(self.response_kind, self.options)
        return payload

    @classmethod
    def from_firestore(cls, data: dict) -> "FormCategory":
        kind = data.get("response_kind", "text")
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            response_kind=kind,
            required=data.get("required", True),
            options=_options_from_firestore(kind, data.get("options", {})),
        )
```

```python
# src/lifeguard/features/forms/__init__.py
from lifeguard.features.forms.schema import (
    BooleanOptions,
    ChoiceOption,
    FormCategory,
    FormField,
    InvalidFormSchemaError,
    NoteOptions,
    ScoreOptions,
    SelectOptions,
    TextOptions,
)

__all__ = [
    "BooleanOptions",
    "ChoiceOption",
    "FormCategory",
    "FormField",
    "InvalidFormSchemaError",
    "NoteOptions",
    "ScoreOptions",
    "SelectOptions",
    "TextOptions",
]
```

Implement `_options_to_firestore()` and `_options_from_firestore()` in the same file so they dispatch by `response_kind` and raise `InvalidFormSchemaError` on unknown kinds.

- [ ] **Step 4: Run the schema tests again**

Run: `python -m unittest discover -s tests/features/forms -p 'test_schema.py' -v`

Expected: PASS with `Ran 3 tests`

- [ ] **Step 5: Commit the shared schema layer**

```bash
git add tests/features/forms/test_schema.py src/lifeguard/features/forms/__init__.py src/lifeguard/features/forms/schema.py
git commit -m "feat: add shared forms schema"
```

## Task 2: Add Generic Response and Session Models

**Files:**
- Create: `src/lifeguard/features/forms/models.py`
- Test: `tests/features/forms/test_models.py`

- [ ] **Step 1: Write the failing model tests**

```python
import unittest


class FormSessionModelTests(unittest.TestCase):
    def test_score_response_round_trips(self) -> None:
        from lifeguard.features.forms.models import FormCategoryResponse

        response = FormCategoryResponse(
            category_id="overall",
            response_kind="score",
            value=4,
            note="Strong fundamentals",
        )

        restored = FormCategoryResponse.from_firestore(response.to_firestore())

        self.assertEqual(restored.value, 4)
        self.assertEqual(restored.note, "Strong fundamentals")

    def test_form_response_session_round_trips(self) -> None:
        from lifeguard.features.forms.models import FormCategoryResponse, FormResponseSession

        session = FormResponseSession(
            id="session-1",
            guild_id=123,
            feature_key="content_review",
            owner_id="submission-1",
            responder_id=456,
            responses=[
                FormCategoryResponse(category_id="overall", response_kind="score", value=5)
            ],
            status="completed",
        )

        restored = FormResponseSession.from_firestore(session.to_firestore())

        self.assertEqual(restored.feature_key, "content_review")
        self.assertEqual(restored.responses[0].category_id, "overall")
```

- [ ] **Step 2: Run the model tests to verify the models do not exist yet**

Run: `python -m unittest discover -s tests/features/forms -p 'test_models.py' -v`

Expected: FAIL with `ImportError` for `lifeguard.features.forms.models`

- [ ] **Step 3: Implement the generic response and session models**

```python
# src/lifeguard/features/forms/models.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal


SessionStatus = Literal["draft", "completed", "cancelled"]


@dataclass
class FormCategoryResponse:
    category_id: str
    response_kind: Literal[
        "score",
        "note",
        "text",
        "boolean",
        "single_select",
        "multi_select",
    ]
    value: int | str | bool | list[str]
    note: str = ""
    reference: str = ""

    def to_firestore(self) -> dict:
        return {
            "category_id": self.category_id,
            "response_kind": self.response_kind,
            "value": self.value,
            "note": self.note,
            "reference": self.reference,
        }

    @classmethod
    def from_firestore(cls, data: dict) -> "FormCategoryResponse":
        return cls(
            category_id=data["category_id"],
            response_kind=data["response_kind"],
            value=data.get("value"),
            note=data.get("note", ""),
            reference=data.get("reference", ""),
        )


@dataclass
class FormResponseSession:
    id: str
    guild_id: int
    feature_key: str
    owner_id: str
    responder_id: int
    responses: list[FormCategoryResponse] = field(default_factory=list)
    status: SessionStatus = "draft"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None

    def to_firestore(self) -> dict:
        return {
            "id": self.id,
            "guild_id": self.guild_id,
            "feature_key": self.feature_key,
            "owner_id": self.owner_id,
            "responder_id": self.responder_id,
            "responses": [item.to_firestore() for item in self.responses],
            "status": self.status,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_firestore(cls, data: dict) -> "FormResponseSession":
        def parse_datetime(value):
            if value is None:
                return None
            if isinstance(value, datetime):
                return value
            return value.to_datetime()

        return cls(
            id=data["id"],
            guild_id=data["guild_id"],
            feature_key=data["feature_key"],
            owner_id=data["owner_id"],
            responder_id=data["responder_id"],
            responses=[
                FormCategoryResponse.from_firestore(item)
                for item in data.get("responses", [])
            ],
            status=data.get("status", "draft"),
            created_at=parse_datetime(data.get("created_at"))
            or datetime.now(timezone.utc),
            completed_at=parse_datetime(data.get("completed_at")),
        )
```

- [ ] **Step 4: Run the model tests again**

Run: `python -m unittest discover -s tests/features/forms -p 'test_models.py' -v`

Expected: PASS with `Ran 2 tests`

- [ ] **Step 5: Commit the generic response/session models**

```bash
git add tests/features/forms/test_models.py src/lifeguard/features/forms/models.py
git commit -m "feat: add generic form response sessions"
```

## Task 3: Add Shared Forms Persistence and Generic UI Helpers

**Files:**
- Create: `src/lifeguard/features/forms/repo.py`
- Create: `src/lifeguard/features/forms/wizard.py`
- Create: `src/lifeguard/features/forms/submission_modal.py`
- Test: `tests/features/forms/test_repo.py`
- Test: `tests/features/forms/test_wizard.py`

- [ ] **Step 1: Write the failing repo and wizard tests**

```python
import unittest
from unittest.mock import MagicMock


class FormSessionRepoTests(unittest.TestCase):
    def test_save_session_uses_shared_collection(self) -> None:
        from lifeguard.features.forms.models import FormResponseSession
        from lifeguard.features.forms.repo import FORMS_SESSIONS_COLLECTION, save_session

        firestore = MagicMock()
        session = FormResponseSession(
            id="session-1",
            guild_id=123,
            feature_key="content_review",
            owner_id="submission-1",
            responder_id=456,
        )

        save_session(firestore, session)

        firestore.collection.assert_called_once_with(FORMS_SESSIONS_COLLECTION)


class FormWizardHelperTests(unittest.TestCase):
    def test_validate_required_text_response(self) -> None:
        from lifeguard.features.forms.models import FormCategoryResponse
        from lifeguard.features.forms.schema import FormCategory, TextOptions
        from lifeguard.features.forms.wizard import validate_category_response

        category = FormCategory(
            id="context",
            name="Context",
            response_kind="text",
            required=True,
            options=TextOptions(style="paragraph"),
        )

        error = validate_category_response(
            category,
            FormCategoryResponse(category_id="context", response_kind="text", value=""),
        )

        self.assertEqual(error, "Context is required.")
```

- [ ] **Step 2: Run the repo and wizard tests to confirm the helpers do not exist yet**

Run: `python -m unittest discover -s tests/features/forms -p 'test_*.py' -v`

Expected: FAIL with import errors for `repo`, `wizard`, or `submission_modal`

- [ ] **Step 3: Implement shared repo and pure wizard helpers**

```python
# src/lifeguard/features/forms/repo.py
from __future__ import annotations

from typing import TYPE_CHECKING

from lifeguard.features.forms.models import FormResponseSession

if TYPE_CHECKING:
    from google.cloud.firestore import Client as FirestoreClient

FORMS_SESSIONS_COLLECTION = "forms_response_sessions"


def save_session(firestore: FirestoreClient, session: FormResponseSession) -> None:
    firestore.collection(FORMS_SESSIONS_COLLECTION).document(session.id).set(
        session.to_firestore(), merge=True
    )


def get_session(
    firestore: FirestoreClient, session_id: str
) -> FormResponseSession | None:
    document = firestore.collection(FORMS_SESSIONS_COLLECTION).document(session_id).get()
    if not document.exists:
        return None
    return FormResponseSession.from_firestore(document.to_dict())
```

```python
# src/lifeguard/features/forms/wizard.py
from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

import discord

from lifeguard.features.forms.models import FormCategoryResponse, FormResponseSession
from lifeguard.features.forms.schema import FormCategory


def validate_category_response(
    category: FormCategory,
    response: FormCategoryResponse,
) -> str | None:
    if category.required and response.value in (None, "", []):
        return f"{category.name} is required."
    return None


def build_summary_lines(responses: list[FormCategoryResponse]) -> list[str]:
    lines: list[str] = []
    for response in responses:
        lines.append(f"{response.category_id}: {response.value}")
    return lines


class FormWizardView(discord.ui.View):
    def __init__(
        self,
        categories: list[FormCategory],
        session: FormResponseSession,
        on_publish_callback: Callable[[FormResponseSession], Coroutine[Any, Any, None]],
        timeout: float = 900.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.categories = categories
        self.session = session
        self.on_publish_callback = on_publish_callback
```

```python
# src/lifeguard/features/forms/submission_modal.py
from __future__ import annotations

import re
from collections.abc import Callable, Coroutine
from typing import Any

import discord

from lifeguard.features.forms.schema import FormField


class FormSubmissionModal(discord.ui.Modal):
    def __init__(
        self,
        title: str,
        fields: list[FormField],
        on_submit_callback: Callable[[discord.Interaction, dict[str, str]], Coroutine[Any, Any, None]],
    ) -> None:
        super().__init__(title=title)
        self.fields = fields
        self.on_submit_callback = on_submit_callback
```

Complete `FormSubmissionModal` in this task with these exact behaviors:

- store created `discord.ui.TextInput` instances in a `_field_inputs` dictionary keyed by field ID
- map `short_text` and `url` to `discord.TextStyle.short`
- map `paragraph` to `discord.TextStyle.paragraph`
- validate `validation_regex` exactly as the current content review modal does
- call `on_submit_callback(interaction, field_values)` only after all validation passes

Complete `FormWizardView` in this task with these exact behaviors:

- maintain `current_step` on the view instance
- render one category at a time for `score`, `boolean`, `single_select`, and `multi_select` using Discord select components
- render `text` and `note` inputs by opening a modal dedicated to the active category
- disable the next/publish action until the active required category has a valid response
- build a summary embed from `build_summary_lines()` before publish
- return the completed `FormResponseSession` unchanged to the publish callback

- [ ] **Step 4: Run the forms tests again**

Run: `python -m unittest discover -s tests/features/forms -p 'test_*.py' -v`

Expected: PASS with schema, model, repo, and helper tests all green

- [ ] **Step 5: Commit the shared forms persistence and UI helpers**

```bash
git add tests/features/forms/test_repo.py tests/features/forms/test_wizard.py src/lifeguard/features/forms/repo.py src/lifeguard/features/forms/wizard.py src/lifeguard/features/forms/submission_modal.py
git commit -m "feat: add shared forms persistence and ui helpers"
```

## Task 4: Migrate Content Review Config to Shared Forms Schema

**Files:**
- Modify: `src/lifeguard/modules/content_review/config.py`
- Modify: `src/lifeguard/modules/content_review/__init__.py`
- Modify: `src/lifeguard/modules/content_review/views/config_ui.py`
- Test: `tests/modules/content_review/test_config_migration.py`

- [ ] **Step 1: Write the failing config migration tests**

```python
import unittest


class ContentReviewConfigMigrationTests(unittest.TestCase):
    def test_from_firestore_reads_legacy_review_categories(self) -> None:
        from lifeguard.modules.content_review.config import ContentReviewConfig

        config = ContentReviewConfig.from_firestore(
            {
                "guild_id": 123,
                "review_categories": [
                    {
                        "id": "overall",
                        "name": "Overall",
                        "response_kind": "score",
                        "options": {"min_value": 1, "max_value": 5, "allow_note": True},
                    }
                ],
            }
        )

        self.assertEqual(config.form_categories[0].id, "overall")
        self.assertEqual(config.form_categories[0].response_kind, "score")

    def test_to_firestore_writes_form_categories_only(self) -> None:
        from lifeguard.features.forms.schema import FormCategory, ScoreOptions
        from lifeguard.modules.content_review.config import ContentReviewConfig

        config = ContentReviewConfig(
            guild_id=123,
            form_categories=[
                FormCategory(
                    id="overall",
                    name="Overall",
                    response_kind="score",
                    options=ScoreOptions(min_value=1, max_value=5, allow_note=True),
                )
            ],
        )

        payload = config.to_firestore()

        self.assertIn("form_categories", payload)
        self.assertNotIn("review_categories", payload)
```

- [ ] **Step 2: Run the config migration tests to verify the old config shape is still wired in**

Run: `python -m unittest discover -s tests/modules/content_review -p 'test_config_migration.py' -v`

Expected: FAIL because `ContentReviewConfig` does not yet expose `form_categories`

- [ ] **Step 3: Refactor content review config to use shared forms types**

```python
# src/lifeguard/modules/content_review/config.py
from lifeguard.features.forms.schema import FormCategory, FormField


@dataclass
class ContentReviewConfig:
    guild_id: int
    enabled: bool = False
    submission_channel_id: int | None = None
    sticky_message_id: int | None = None
    ticket_category_id: int | None = None
    reviewer_role_ids: list[int] = field(default_factory=list)
    submission_fields: list[FormField] = field(default_factory=list)
    form_categories: list[FormCategory] = field(default_factory=list)
```

In `from_firestore()`, read `form_categories` first, then fall back to legacy `review_categories` if the new key is missing. In `to_firestore()`, write only `form_categories`.

Update `views/config_ui.py` so menus, add/remove actions, and previews all import `FormCategory` and `FormField` from the shared forms package.

- [ ] **Step 4: Run the config migration tests again**

Run: `python -m unittest discover -s tests/modules/content_review -p 'test_config_migration.py' -v`

Expected: PASS with `Ran 2 tests`

- [ ] **Step 5: Commit the content review config migration**

```bash
git add tests/modules/content_review/test_config_migration.py src/lifeguard/modules/content_review/config.py src/lifeguard/modules/content_review/__init__.py src/lifeguard/modules/content_review/views/config_ui.py
git commit -m "refactor: migrate content review config to shared forms schema"
```

## Task 5: Add the Content Review Translation Layer

**Files:**
- Create: `src/lifeguard/modules/content_review/forms_translation.py`
- Modify: `src/lifeguard/modules/content_review/models.py`
- Test: `tests/modules/content_review/test_forms_translation.py`

- [ ] **Step 1: Write the failing translation tests**

```python
import unittest


class ContentReviewFormsTranslationTests(unittest.TestCase):
    def test_score_session_translates_to_review_payload(self) -> None:
        from lifeguard.features.forms.models import FormCategoryResponse, FormResponseSession
        from lifeguard.modules.content_review.forms_translation import session_to_review_payload

        session = FormResponseSession(
            id="session-1",
            guild_id=123,
            feature_key="content_review",
            owner_id="submission-1",
            responder_id=456,
            responses=[
                FormCategoryResponse(
                    category_id="overall",
                    response_kind="score",
                    value=4,
                    note="Solid progress",
                    reference="01:23",
                )
            ],
            status="completed",
        )

        payload = session_to_review_payload(session)

        self.assertEqual(payload.scores, {"overall": 4})
        self.assertEqual(payload.notes["overall"].feedback, "Solid progress")
        self.assertEqual(payload.notes["overall"].reference, "01:23")
```

- [ ] **Step 2: Run the translation tests to confirm the adapter does not exist yet**

Run: `python -m unittest discover -s tests/modules/content_review -p 'test_forms_translation.py' -v`

Expected: FAIL with `ModuleNotFoundError` for `forms_translation`

- [ ] **Step 3: Implement the translation helpers**

```python
# src/lifeguard/modules/content_review/forms_translation.py
from __future__ import annotations

from dataclasses import dataclass, field

from lifeguard.features.forms.models import FormCategoryResponse, FormResponseSession
from lifeguard.modules.content_review.models import ReviewNote


@dataclass
class ReviewPayload:
    scores: dict[str, int] = field(default_factory=dict)
    notes: dict[str, ReviewNote] = field(default_factory=dict)


def session_to_review_payload(session: FormResponseSession) -> ReviewPayload:
    payload = ReviewPayload()
    for response in session.responses:
        if response.response_kind != "score":
            continue
        payload.scores[response.category_id] = int(response.value)
        if response.note:
            payload.notes[response.category_id] = ReviewNote(
                reference=response.reference,
                feedback=response.note,
            )
    return payload
```

Add a second helper in the same file named `build_review_session_draft()` that takes `submission_id`, `guild_id`, `reviewer_id`, and `config.form_categories`, then returns a draft `FormResponseSession` with `feature_key="content_review"`, `owner_id=submission_id`, empty `responses`, and `status="draft"`. Keep review publishing logic in `cog.py`.

- [ ] **Step 4: Run the translation tests again**

Run: `python -m unittest discover -s tests/modules/content_review -p 'test_forms_translation.py' -v`

Expected: PASS with `Ran 1 test`

- [ ] **Step 5: Commit the translation layer**

```bash
git add tests/modules/content_review/test_forms_translation.py src/lifeguard/modules/content_review/forms_translation.py src/lifeguard/modules/content_review/models.py
git commit -m "feat: add content review forms translation layer"
```

## Task 6: Replace the Review-Specific Wizard and Modal in Content Review

**Files:**
- Modify: `src/lifeguard/modules/content_review/cog.py`
- Delete: `src/lifeguard/modules/content_review/views/review_wizard.py`
- Delete: `src/lifeguard/modules/content_review/views/submission_modal.py`
- Test: `tests/modules/content_review/test_review_flow_compat.py`

- [ ] **Step 1: Write the failing compatibility tests**

```python
import unittest


class ContentReviewFlowCompatibilityTests(unittest.TestCase):
    def test_build_review_session_draft_preserves_category_order(self) -> None:
        from lifeguard.features.forms.schema import FormCategory, ScoreOptions
        from lifeguard.modules.content_review.forms_translation import build_review_session_draft

        categories = [
            FormCategory(id="overall", name="Overall", response_kind="score", options=ScoreOptions()),
            FormCategory(id="teamplay", name="Teamplay", response_kind="score", options=ScoreOptions()),
        ]

        draft = build_review_session_draft(
            submission_id="submission-1",
            guild_id=123,
            responder_id=456,
            categories=categories,
        )

        self.assertEqual(draft.owner_id, "submission-1")
        self.assertEqual(draft.feature_key, "content_review")
        self.assertEqual(draft.status, "draft")
        self.assertEqual(draft.responses, [])
        self.assertEqual([item.id for item in categories], ["overall", "teamplay"])
```

- [ ] **Step 2: Run the compatibility tests to confirm `ContentReviewCog` still imports the old view classes**

Run: `python -m unittest discover -s tests/modules/content_review -p 'test_review_flow_compat.py' -v`

Expected: FAIL with `ImportError` or `AttributeError` because `build_review_session_draft()` does not exist yet and `ContentReviewCog` still depends on the old review-specific views

- [ ] **Step 3: Replace wizard and modal imports in the cog**

```python
# src/lifeguard/modules/content_review/cog.py
from lifeguard.features.forms.models import FormResponseSession
from lifeguard.features.forms.submission_modal import FormSubmissionModal
from lifeguard.features.forms.wizard import FormWizardView
from lifeguard.modules.content_review.forms_translation import session_to_review_payload
```

In the review-start flow:

- build a `FormResponseSession` draft instead of `DraftReview`
- pass `config.form_categories` into `FormWizardView`
- on publish, translate the generic session with `session_to_review_payload()`
- keep existing embed generation, repo writes, and DM behavior unchanged

In the submission flow:

- replace `SubmissionModal(config, on_submit)` with `FormSubmissionModal(config.modal_title, config.submission_fields, on_submit)`

Delete the old `review_wizard.py` and `submission_modal.py` once `cog.py` no longer imports them.

- [ ] **Step 4: Run the content review compatibility tests again**

Run: `python -m unittest discover -s tests/modules/content_review -p 'test_review_flow_compat.py' -v`

Expected: PASS with the new generic session path exercised by the tests

- [ ] **Step 5: Commit the generic content review integration**

```bash
git add tests/modules/content_review/test_review_flow_compat.py src/lifeguard/modules/content_review/cog.py src/lifeguard/features/forms/submission_modal.py src/lifeguard/features/forms/wizard.py src/lifeguard/modules/content_review/forms_translation.py
git rm src/lifeguard/modules/content_review/views/review_wizard.py src/lifeguard/modules/content_review/views/submission_modal.py
git commit -m "refactor: move content review onto shared forms engine"
```

## Task 7: Wire Shared Forms Persistence into the Review Completion Path

**Files:**
- Modify: `src/lifeguard/modules/content_review/cog.py`
- Modify: `src/lifeguard/modules/content_review/repo.py`
- Modify: `tests/modules/content_review/test_review_flow_compat.py`
- Modify: `tests/features/forms/test_repo.py`

- [ ] **Step 1: Write the failing persistence compatibility test**

```python
import unittest
from unittest.mock import MagicMock


class ContentReviewPersistenceCompatibilityTests(unittest.TestCase):
    def test_completed_review_saves_generic_form_session(self) -> None:
        from lifeguard.features.forms.models import FormCategoryResponse, FormResponseSession
        from lifeguard.features.forms.repo import save_session

        firestore = MagicMock()
        session = FormResponseSession(
            id="session-1",
            guild_id=123,
            feature_key="content_review",
            owner_id="submission-1",
            responder_id=456,
            responses=[
                FormCategoryResponse(category_id="overall", response_kind="score", value=5)
            ],
            status="completed",
        )

        save_session(firestore, session)

        firestore.collection.assert_called_once_with("forms_response_sessions")
```

- [ ] **Step 2: Run the persistence tests to capture the missing session save in the review completion path**

Run: `python -m unittest discover -s tests -p 'test_repo.py' -v`

Expected: PASS for the repo helper itself but FAIL for the content review compatibility test until `cog.py` saves the session before or alongside review publishing

- [ ] **Step 3: Save the generic session during review completion**

Add a narrow helper in `ContentReviewCog` that takes the completed `FormResponseSession`, marks `completed_at`, saves it through `lifeguard.features.forms.repo.save_session()`, then translates it into the existing review-specific persistence path.

```python
session.status = "completed"
session.completed_at = datetime.now(timezone.utc)
forms_repo.save_session(self.firestore, session)
review_payload = session_to_review_payload(session)
```

Keep the existing review-specific repo writes intact after the new session save so current behavior remains unchanged.

- [ ] **Step 4: Run the focused compatibility tests again**

Run: `python -m unittest discover -s tests/modules/content_review -p 'test_review_flow_compat.py' -v`

Expected: PASS with assertions that the generic session is saved and the existing review output path still executes

- [ ] **Step 5: Commit the shared session persistence wiring**

```bash
git add src/lifeguard/modules/content_review/cog.py src/lifeguard/modules/content_review/repo.py tests/modules/content_review/test_review_flow_compat.py tests/features/forms/test_repo.py
git commit -m "feat: persist generic form sessions in content review"
```

## Task 8: Update Documentation and Remove Transitional Names

**Files:**
- Modify: `docs/ModuleDevelopment.md`
- Modify: `docs/Architecture.md`
- Modify: `src/lifeguard/modules/content_review/views/config_ui.py`

- [ ] **Step 1: Write the failing documentation grep check**

Run: `git grep -n "ReviewCategory\|review_wizard\|ReviewWizardView" -- docs src/lifeguard/modules/content_review/views/config_ui.py`

Expected: output includes one or more matches showing the old review-specific names are still present in docs or admin-facing config copy.

- [ ] **Step 2: Update the docs and UI labels to the new shared forms language**

Add these points to the docs:

```markdown
- Use `lifeguard.features.forms` for configurable submission fields and category-based flows.
- Keep module-specific publish logic in the module, not in the shared forms engine.
- Prefer `FormCategory` over review-specific category classes for new modules.
```

Update any admin-facing copy in `config_ui.py` that still hardcodes review-specific category terminology where generic wording is now correct.

- [ ] **Step 3: Run the focused regression tests**

Run: `python -m unittest discover -s tests/features/forms -p 'test_*.py' -v`

Run: `python -m unittest discover -s tests/modules/content_review -p 'test_*.py' -v`

Expected: PASS across the new shared forms tests and content review compatibility tests

- [ ] **Step 4: Run a final narrow repo-wide verification**

Run: `python -m unittest discover -s tests -v`

Expected: PASS with existing feature and config-shell tests still green

- [ ] **Step 5: Commit the documentation and cleanup pass**

```bash
git add docs/ModuleDevelopment.md docs/Architecture.md src/lifeguard/modules/content_review/views/config_ui.py
git commit -m "docs: document shared forms engine"
```

## Self-Review Checklist

- Spec coverage: this plan covers the shared forms package, supported response kinds, generic stored response sessions, config migration, content review translation, compatibility preservation, and documentation updates.
- Placeholder scan: no task uses `TBD`, `TODO`, or undefined later work; all steps point to concrete files and commands.
- Type consistency: the plan uses `FormField`, `FormCategory`, `FormCategoryResponse`, `FormResponseSession`, and `FormWizardView` consistently across tasks.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-05-generic-forms-engine-implementation-plan.md`. Two execution options:

1. Subagent-Driven (recommended) - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. Inline Execution - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?