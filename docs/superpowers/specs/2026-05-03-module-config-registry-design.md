# Module Config Registry Design

## Summary

Lifeguard should keep a shared configuration shell while moving module registration, metadata, and config behavior into independently discoverable module packages. The target model is package auto-discovery under `lifeguard.modules`, dynamic registration into a shared runtime registry, and global `/config`, `/enable-feature`, and `/disable-feature` commands that dispatch through that registry instead of hardcoded module branches.

This design removes the current requirement to edit central bot and config-shell code whenever a module is added or removed. It also creates the right seam for a future subscription model by separating module presence, guild configuration state, and feature entitlement.

## Current Problem

The current implementation is only partially decoupled.

- Runtime module loading is hardcoded in `src/lifeguard/bot.py`.
- Shared config command routing is hardcoded in `src/lifeguard/cogs/config_cog.py`.
- Shared config UI buttons are hardcoded in `src/lifeguard/cogs/config_views.py`.
- Feature interfaces exist, but they are split by module type and still require the shell to know specific modules by name.

That means a module cannot currently be added, removed, or deployed independently without editing central files. It also means future subscription gating would be layered on top of existing hardcoded routing instead of using a single authoritative feature registry.

## Goals

- Keep one shared `/config` shell for admins.
- Keep global `/enable-feature` and `/disable-feature` commands.
- Allow modules to register independently through package auto-discovery.
- Ensure adding or removing a module does not require edits outside that module package.
- Make the config shell generic so it renders and dispatches through discovered metadata.
- Separate feature availability from feature implementation so subscription logic can be added later.
- Preserve stored configuration and historical state for modules that become unavailable or are no longer installed.

## Non-Goals

- Building the full subscription system now.
- Moving to an external plugin framework or Python package entry-point system.
- Automatically deleting Firestore data when a module is removed.
- Rewriting module-specific configuration UIs to a common internal implementation.

## Options Considered

### 1. Central Manifest File

Each module would expose metadata, but a central manifest file would still import and register all features.

Pros:

- Lowest implementation risk.
- Simple migration from the current hardcoded structure.

Cons:

- Still requires shared-code edits when modules are added or removed.
- Does not satisfy the desired deletion and deployment boundary.

### 2. Auto-Discovery Plus Per-Module Manifest

Each module package exports a manifest, and the bot discovers modules dynamically under `lifeguard.modules`.

Pros:

- Matches the desired module isolation boundary.
- Keeps the shared shell while removing hardcoded module knowledge from it.
- Provides a clean seam for future subscription gating.
- Keeps the runtime architecture simple enough for the current codebase.

Cons:

- Requires a new registry layer and a migration of existing modules onto it.
- Requires generic shell rendering instead of static feature buttons.

### 3. External Plugin System

Modules would be loaded through entry points or external configuration rather than package scanning.

Pros:

- Maximum flexibility for future deployment models.

Cons:

- More packaging and operational complexity than the current project needs.
- Solves problems the current codebase does not yet have.

## Recommended Approach

Use auto-discovery plus per-module manifests.

This option removes the current coupling at the real problem points without introducing plugin-framework complexity too early. It also supports the future subscription direction because the shared shell can ask a dedicated availability layer whether a module is visible, enabled, entitled, or unavailable without coupling those rules to the module implementation.

## Architecture

Add a feature platform layer responsible for module discovery, runtime registration, and availability resolution.

At startup, the bot scans packages under `lifeguard.modules`, imports each module package, and collects valid feature manifests. The bot then loads each module's cog through the manifest and stores the resulting registry on the bot instance.

The shared config shell becomes a generic presenter and dispatcher. It no longer resolves `ContentReviewCog`, `TimeImpersonatorCog`, or `VoiceLobbyCog` directly. Instead, it resolves a feature by key from the registry and invokes generic config operations through a shared adapter interface.

Subscription logic is not implemented yet, but the architecture reserves a dedicated availability resolver so the shell can later distinguish between these states without changing module code:

- available
- enabled
- disabled
- not entitled
- unavailable

## Core Components

### FeatureManifest

Each module exports one manifest object from a predictable location such as `manifest.py` or package `__init__.py`.

The manifest should be declarative. It should contain:

- `feature_key`
- `display_name`
- `description`
- `emoji` or icon metadata
- `requires_setup`
- cog factory
- config adapter factory

The manifest should not hold live bot state.

### FeatureRegistry

The registry is built at startup from discovered manifests.

Its responsibilities are:

- index manifests by feature key
- expose discovered features for `/config` and command autocomplete
- resolve a feature's live config adapter on demand
- provide the shared shell with a single authoritative source of feature metadata

`ConfigCog` and the bot factory should depend on this registry instead of naming modules directly.

### FeatureConfigAdapter

This is the normalized shell-facing interface for feature configuration.

The shared shell should only need these operations:

- `show_menu`
- `show_status`
- `enable`
- `disable`
- optional `show_setup`

Modules can keep their own internal views and specialized config flows. The adapter exists so the shell only needs one consistent contract.

### FeatureAvailabilityResolver

This component combines:

- discovered modules
- guild configuration or historical state
- future entitlement or subscription state

The shell should use it before rendering a feature entry or executing enable and disable commands.

This keeps subscription logic out of module code and out of the shell rendering layer.

## Data Flow

### Startup

1. Bot startup scans `lifeguard.modules`.
2. Each valid module package exposes a manifest.
3. The registry indexes manifests.
4. The bot loads cogs from manifest factories.
5. The registry is stored on the bot instance for config-shell and command use.

### Shared `/config`

1. An admin opens `/config`.
2. `ConfigCog` asks the registry for visible features.
3. The shared shell renders feature entries from registry metadata instead of fixed buttons.
4. When a feature is selected, `ConfigCog` resolves its config adapter.
5. The adapter handles setup, menu rendering, status, enable, disable, and nested module-specific flows.

### Shared `/enable-feature` and `/disable-feature`

1. Autocomplete is generated from the discovered registry.
2. The chosen feature key is resolved through the registry.
3. `ConfigCog` dispatches to the adapter instead of hardcoded module branches.

### Availability Resolution

1. Before the shell renders a feature or executes a state-changing action, it asks the availability resolver for the feature's effective guild status.
2. The resolver returns state such as available, enabled, disabled, not entitled, or unavailable.
3. The shell renders the correct affordance without forcing the module to implement subscription concerns.

## Removal and Subscription Semantics

Module absence should not imply data deletion.

If a module is removed from `lifeguard.modules`, the bot should continue booting and should preserve any stored Firestore config or historical state associated with that module. The shared shell should be able to represent the module as unavailable rather than silently hiding it or treating it as permanently uninstalled.

This is the right default for future subscriptions because plan downgrades and reactivation flows generally need suspend-and-resume behavior, not delete-and-recreate behavior.

Destructive cleanup, if ever needed, should be an explicit maintenance or admin operation rather than a side effect of module removal.

## Migration Plan

Implement the refactor in two passes.

### Pass 1: Introduce the Registry Layer

- Add the discovery and registry components.
- Add the shell-facing adapter contract.
- Keep the existing shell working while allowing modules to start registering through manifests.
- Allow the shell to read from the registry even if some existing code paths are still transitional.

### Pass 2: Migrate Existing Modules and Remove Hardcoding

- Convert `content_review`, `time_impersonator`, and `voice_lobby` to manifest-based registration.
- Replace hardcoded module buttons with dynamically rendered entries.
- Replace hardcoded command routing with registry dispatch.
- Remove explicit module loading from `bot.py`.
- Remove feature-specific branches from the shared config shell.

This keeps the blast radius manageable and allows incremental migration.

## Failure Handling

- If discovery finds a malformed module, log it, skip registration for that module, and continue booting.
- If a module existed historically but is not currently installed, render it as unavailable instead of erroring or silently dropping it.
- If a manifest is valid but a cog or adapter factory fails during startup, treat that as a registration failure and skip the feature for the current process.
- The shared shell should never need feature-specific exception branches for missing modules.

## Testing Strategy

The refactor should be verified at three levels.

### Discovery and Registry Tests

- discovery finds valid module manifests under `lifeguard.modules`
- malformed modules are skipped without crashing startup
- duplicate feature keys fail predictably

### Shell Dispatch Tests

- `/config` renders entries from registry metadata
- `/enable-feature` and `/disable-feature` autocomplete is registry-driven
- selecting a feature dispatches to the correct adapter
- a missing or unavailable module produces the correct generic shell state

### Integration Tests

- existing modules still load and behave correctly after migration
- removing a module package does not break bot startup
- historical config for a removed module appears as unavailable when appropriate
- future entitlement checks can be inserted at the availability resolver boundary without changing module adapters

## Design Constraints

- The shared shell owns presentation and dispatch, not feature-specific persistence or behavior.
- Modules own their metadata, cog loading, setup behavior, and config workflow implementation.
- A new module should become configurable by adding its package and manifest, not by editing central routing code.
- The registry must remain authoritative for both config-shell rendering and global enable and disable shortcuts so those paths cannot drift apart.

## Outcome

After this refactor, Lifeguard will keep a single shared admin configuration surface while allowing each module to be developed, deployed, or removed independently. The shell becomes generic, module behavior stays local, and the system gains a clean path toward subscription-based feature availability without another structural rewrite.