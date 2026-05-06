# Architecture Overview

## High-Level Structure

```
src/lifeguard/
├── __init__.py          # Package version
├── __main__.py          # Entry point (python -m lifeguard)
├── bot.py               # Bot factory and event setup
├── config.py            # Environment configuration
├── exceptions.py        # Shared exceptions
├── utils.py             # Shared utilities
├── logging_config.py    # Logging setup
├── firestore_client.py  # Firebase initialization
├── cogs/                # Core Discord cogs
│   ├── core.py          # Basic commands (ping, purge)
│   ├── config_cog.py    # /config, /enable-feature, /disable-feature
│   └── config_views.py  # Cross-cutting config UI views
├── db/                  # SQLAlchemy layer (legacy/unused)
└── modules/             # Feature modules
    ├── content_review/   # Submission review system
    ├── time_impersonator/# Dynamic Discord timestamps via webhook
    └── voice_lobby/      # Temporary voice channels from entry channel
```

## Data Flow

```
Discord Event
    ↓
discord.py Bot
    ↓
Cog Command Handler
    ↓
Repository Layer (repo.py)
    ↓
Firestore Client
```

## Key Components

### Bot Factory (`bot.py`)
Creates the discord.py `Bot` instance with:
- Intent configuration
- Event handlers (`on_ready`, `setup_hook`, `close`)
- Core cog registration plus manifest-driven module bootstrap
- Shared resources (HTTP session, Firestore client)

During `setup_hook`, Lifeguard discovers feature manifests under `lifeguard.modules`,
builds a `FeatureRegistry`, stores it on `bot.lifeguard_features`, and loads each
module cog through its manifest factory.

### Configuration (`config.py`)
Frozen dataclass loaded from environment:
- `BOT_ENV` - `"production"` (default) or `"test"` — selects which env files to load
- `DISCORD_TOKEN` - Bot authentication
- `GUILD_ID` - Optional guild for fast command sync (production)
- `TEST_GUILD_ID` - Dev/test guild for command sync when `BOT_ENV=test`
- `FIREBASE_*` - Firestore configuration

When `BOT_ENV=test`, the bot loads `.env.test` first, then `.env` as fallback.
Use `config.active_guild_id` to get the appropriate guild for the current environment.

### Module Architecture
Each module is self-contained:

| Component | Responsibility |
|-----------|---------------|
| `cog.py` | Discord slash commands, event handling |
| `models.py` | Data structures, Firestore serialization |
| `repo.py` | Database operations (CRUD) |
| `config.py` | Module-specific settings (optional) |
| `views/` | Discord UI components (optional) |

### Shared Resources
Bot instance carries shared resources as attributes:
- `bot.lifeguard_http_session` - aiohttp session for API calls
- `bot.lifeguard_firestore` - Firestore client

## Shared Forms Boundary

`lifeguard.features.forms` is the shared path for configurable forms and category-based
response flows. It owns the reusable form schema, validation helpers, Discord wizard
flow, and persisted form response sessions that multiple modules can use.

Modules still own how those responses are interpreted and published. For example,
`content_review` translates generic form responses into review-specific outputs and
keeps its sticky-message, ticket, embed, and publishing behavior inside the module
package instead of pushing that logic into the shared forms engine.

## Feature Registry and Shared Config Shell

All feature management still flows through `/config`, `/enable-feature`, and
`/disable-feature`, but the central shell is now registry-backed instead of
hardcoded.

### Runtime flow
1. `lifeguard.features.discovery` scans `lifeguard.modules` for `manifest.py`.
2. `lifeguard.features.registry.FeatureRegistry` indexes discovered manifests.
3. `lifeguard.features.bootstrap.register_module_features()` loads module cogs.
4. `ConfigCog` resolves feature metadata, autocomplete, and adapters from the registry.
5. Feature-specific configuration UI stays inside each module package.

### Availability resolution

`lifeguard.features.availability.resolve_feature_entries()` combines discovered
manifests with `GuildSettings.known_feature_keys` so the shared shell can still
represent previously configured modules that are no longer installed.

Unavailable historical entries remain visible to the shell as unavailable rather
than disappearing silently.

## Feature Flags
Guild-level feature toggles stored in Firestore:
- Each module has its own config collection (`content_review_configs`, `voice_lobby_configs`, etc.)
- Checked via decorators (`@require_content_review()`, `@require_time_impersonator()`)
- Raise `FeatureDisabledError` when disabled
- Toggled via module-owned config adapters behind `/config` or the `/enable-feature` / `/disable-feature` shortcuts

## Database Layers

### Primary: Firestore
- Document-based storage
- Collections per feature (`content_review_configs`, `content_review_submissions`, etc.)
- Repository pattern for data access

### Legacy: SQLAlchemy (`db/`)
- Originally planned for legacy relational data storage
- Currently unused - kept for potential future use
