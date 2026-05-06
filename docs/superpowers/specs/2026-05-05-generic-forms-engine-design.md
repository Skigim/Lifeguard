# Generic Forms Engine Design

## Summary

Lifeguard should replace the review-specific category and wizard abstractions inside `content_review` with a shared forms engine under `lifeguard.features.forms`. The new engine should support generic step-based form categories and generic persisted response sessions, while preserving the current content review workflow and outputs through a compatibility layer.

This design removes the current coupling between `ReviewCategory` and `ReviewWizardView` and creates a reusable path for future modules that need scored reviews, guided checklists, moderation forms, or configurable questionnaires.

## Current Problem

The current `content_review` module owns abstractions that are more general than the feature they live in.

- `SubmissionField` is already a generic intake field, but it is defined inside `content_review`.
- `ReviewCategory` is defined as a review-specific scoring primitive instead of a reusable step/category schema.
- `ReviewWizardView` is implemented as a review-specific multi-step engine rather than a generic category-response wizard.
- Runtime draft state is tied to review semantics even though most of the flow is generic form navigation, validation, and response capture.
- Future modules would need to duplicate or fork review-specific code to build their own category-based flows.

That means the current codebase cannot add new configurable form-based modules cleanly without either copying `content_review` internals or making more feature-specific exceptions in shared code.

## Goals

- Replace `ReviewCategory` with a generic `FormCategory` model.
- Replace `ReviewWizardView` with a generic category-driven wizard.
- Support these response kinds in the first implementation:
  - `score`
  - `note`
  - `text`
  - `boolean`
  - `single_select`
  - `multi_select`
- Add generic persisted response/session models that future modules can reuse.
- Migrate persisted config from `review_categories` to `form_categories`.
- Preserve the current content review workflow, publish behavior, and review-facing outputs.
- Keep the forms engine internal shared infrastructure rather than a standalone feature manifest.

## Non-Goals

- Turning all of `content_review` into a fully generic module in one pass.
- Replacing content review leaderboards, profiles, or review-specific reporting with generic equivalents.
- Building a visual form designer beyond the current config flows.
- Generalizing every existing Firestore document in the module during the first refactor.

## Options Considered

### 1. Generic UI Only

Generalize the category schema and wizard UI, but keep review-specific runtime and persistence models.

Pros:

- Smallest change set.
- Lowest migration risk.

Cons:

- Leaves generic reuse incomplete.
- Future modules still need custom storage semantics.

### 2. Generic UI Plus Generic Stored Responses

Introduce a shared forms package with generic schema, generic wizard state, and generic persisted response sessions. Content review uses this engine and translates generic responses into its review-specific outputs.

Pros:

- Creates a real reusable platform boundary.
- Supports future form-based modules without another structural rewrite.
- Preserves current content review behavior while removing review-specific ownership from the generic flow.

Cons:

- Larger change than a UI-only refactor.
- Requires config migration and new persistence contracts.

### 3. Full Forms Platform Including Orchestration

Generalize schema, UI, persistence, and all submission/review orchestration into a standalone forms subsystem.

Pros:

- Most complete long-term abstraction.

Cons:

- Too large for one refactor.
- Forces unnecessary changes into content review business logic before the new boundary is proven.

## Recommended Approach

Use option 2: generic UI plus generic stored responses.

This is the smallest design that meaningfully separates the generic forms engine from content review. It moves the reusable primitives into shared infrastructure, adds durable generic response/session storage for future modules, and keeps review-specific publishing, embeds, and reporting local to `content_review`.

## Architecture

Add a shared package under `lifeguard.features.forms`.

This package owns:

- generic form schema models
- generic category response models
- generic response/session serialization
- generic category wizard UI
- validation helpers for supported response kinds
- migration helpers for config documents that rename `review_categories` to `form_categories`

`content_review` stops defining `ReviewCategory` and stops owning the review-specific wizard implementation. Instead, it provides review-oriented presets, translation helpers, and publishing logic on top of the shared forms package.

The resulting ownership boundary is:

- `lifeguard.features.forms`: generic schema, runtime capture, storage, validation, and wizard mechanics
- `lifeguard.modules.content_review`: feature-specific commands, setup UI, publish behavior, embeds, stats, and compatibility translation

## Core Components

### FormCategory

`FormCategory` replaces `ReviewCategory`.

Each category includes:

- `id`
- `name`
- `description`
- `response_kind`
- `required`
- response-kind-specific options

The response-kind-specific options are typed by kind rather than being a loose dictionary.

Examples:

- `score` categories define score bounds and note rules
- `text` categories define text style and optional validation hints
- `boolean` categories define display labels
- `single_select` and `multi_select` categories define option lists and selection constraints

### FormCategoryResponse

A generic runtime and persisted answer to one `FormCategory`.

It includes:

- `category_id`
- `response_kind`
- normalized response payload
- optional metadata needed for validation or rendering

The response payload is explicit per kind so deserialization can reject invalid or unknown shapes early.

### FormResponseSession

A generic container for all category responses produced by a wizard run.

It includes:

- session ID
- guild ID
- feature key or owner context
- subject identifiers needed by the owning module
- responder/user ID
- ordered category responses
- created/completed timestamps
- status

This session becomes the authoritative generic record of a completed category-based form flow.

### FormWizardView

A generic step-based Discord view that renders one category at a time, validates responses, tracks progress, and produces a `FormResponseSession` or in-memory draft equivalent before persistence.

It owns:

- step navigation
- per-kind component rendering
- validation that required responses exist before continuing or publishing
- summary rendering based on generic responses

It does not own review-specific publishing logic.

### Content Review Translation Layer

`content_review` keeps a compatibility layer that:

- maps existing config into generic form category definitions
- maps generic response sessions back into review-specific score and note structures
- preserves current review embeds, completion flows, and profile updates

This preserves the current review method without keeping review-specific primitives as the base abstraction.

## Schema Design

The generic forms engine should support these first-class response kinds:

- `score`
- `note`
- `text`
- `boolean`
- `single_select`
- `multi_select`

“First-class” means each response kind has:

- an explicit enum value in the schema
- typed config/options
- dedicated rendering logic in the wizard
- dedicated validation rules
- explicit serialization and deserialization behavior

The engine should not treat these as arbitrary strings or feature-specific conditionals.

The schema should be extensible, but the first implementation should only validate and render the approved kinds above.

## Data Flow

### Config Loading

1. A guild config document is loaded for `content_review`.
2. Migration-aware deserialization reads either `form_categories` or legacy `review_categories` during rollout.
3. The config is normalized into shared `FormCategory` instances.
4. Once saved again, the config is written in the new `form_categories` shape.

### Submission and Review Flow

1. A user starts the content review flow through the existing command or button path.
2. `content_review` still owns the feature-specific entrypoints and submit/publish flow.
3. The shared `FormWizardView` renders the category sequence from `FormCategory` definitions.
4. The wizard collects generic responses and builds a `FormResponseSession`.
5. The session is persisted through shared forms storage.
6. `content_review` translates the generic session into its existing review-facing structures for embeds, completion messaging, scoring, and profile updates.

### Future Module Reuse

A future module can define its own `FormCategory` list and consume the same shared wizard and session persistence without importing `content_review` internals.

## Persistence Strategy

Introduce shared persistence for generic form response sessions.

This does not require all existing `content_review` documents to disappear immediately. The forms session becomes the reusable system of record for the category-response flow, while `content_review` can continue to write or derive review-facing records needed by current features.

This preserves compatibility while establishing a shared persistence contract for future modules.

## Migration Plan

Implement the refactor in staged passes.

### Pass 1: Shared Forms Package

- add `lifeguard.features.forms`
- move generic field/category schema into the shared package
- add response-kind enums and typed option models
- add generic wizard runtime state and view
- add shared generic response/session models

### Pass 2: Content Review Integration

- replace `ReviewCategory` usage with `FormCategory`
- replace `ReviewWizardView` with shared `FormWizardView`
- add translation helpers inside `content_review`
- keep current review publishing and reporting behavior intact

### Pass 3: Config Migration

- read legacy `review_categories`
- write `form_categories`
- backfill existing documents as they are touched or through an explicit migration path
- add tests proving legacy configs still load during rollout

### Pass 4: Cleanup

- remove deprecated review-specific category and wizard code
- remove transitional compatibility reads once persisted configs are migrated and verified

## Failure Handling

- Invalid `response_kind` values fail during config deserialization with a clear admin-facing error.
- Invalid category option payloads fail validation before the wizard runs.
- The wizard must not allow publish/complete while required category responses are missing.
- Migration writes must not discard legacy data until the new config shape is written successfully.
- If a migrated config cannot be normalized, `content_review` should fail closed with a clear configuration error instead of publishing partial or incorrect reviews.

## Testing Strategy

Add coverage at these levels.

### Schema and Serialization Tests

- each supported `response_kind` round-trips through serialization
- invalid kinds or invalid option payloads are rejected predictably
- generic response payloads deserialize into the correct typed model

### Wizard Tests

- the wizard renders and validates each response kind correctly
- required responses block forward progress or publish when missing
- summary rendering reflects the stored generic responses

### Migration Tests

- legacy `review_categories` config loads successfully
- migrated config writes `form_categories`
- old and new shapes do not silently diverge during rollout

### Content Review Compatibility Tests

- the content review flow still produces the same effective score and note outputs
- existing publish behavior and review completion logic remain intact
- existing reporting flows continue to work when driven from generic response sessions

## Design Constraints

- The shared forms engine must stay feature-agnostic.
- `content_review` may depend on the shared forms engine, but the shared engine must not depend on `content_review`.
- Generic session persistence should be reusable by future modules without importing review-specific models.
- The first implementation should support the approved response kinds only, even if the schema is extensible.
- The refactor must preserve the current content review method from an admin and reviewer perspective.

## Outcome

After this refactor, Lifeguard will have a reusable internal forms engine for category-based workflows, and `content_review` will become a consumer of that engine rather than its owner. The project gains a clean path for future form-driven modules while preserving the current review experience and behavior during the migration.