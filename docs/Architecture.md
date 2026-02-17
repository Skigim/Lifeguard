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
    ├── albion/           # Albion Online integration
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
- Cog registration
- Shared resources (HTTP session, Firestore client)

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

## Central Configuration Menu (`/config`)

All feature management flows through the `/config` slash command, which is
hosted in `ConfigCog` (`cogs/config_cog.py`). The menu hierarchy:

```
/config
├── General Settings        → Bot admin roles
├── Content Review          → Enable/disable, sticky, roles, form, settings
├── Time Impersonator       → Enable/disable, status
├── Voice Lobby             → Enable/disable, entry channel, defaults, roles
└── Albion Features         → Enable/disable prices & builds, status
```

### Key principles
1. **Every module gets a sub-menu** — each feature is wired into
   `ConfigFeatureSelectView` as its own button.
2. **Enable/disable lives inside the sub-menu** — users can toggle a feature
   on or off from within its config page. No feature blocks access to its
   own config when disabled; instead it shows an "Enable" action.
3. **`/enable-feature` and `/disable-feature` are convenience shortcuts** —
   they provide quick autocomplete-driven access but ultimately call the
   same enable/disable helpers used by the config UI.
4. **Config views call back to the cog** — all views hold a reference to the
   cog and delegate logic to `_show_*` / `_enable_*` / `_disable_*` methods.

### Adding a new feature to the config menu
See `docs/ModuleDevelopment.md` § "Wiring into the Config Menu".

## Feature Flags
Guild-level feature toggles stored in Firestore:
- Each module has its own config collection (`content_review_configs`, `voice_lobby_configs`, etc.)
- Checked via decorators (`@require_content_review()`, `@require_time_impersonator()`)
- Raise `FeatureDisabledError` when disabled
- Toggled via the `/config` sub-menus or the `/enable-feature` / `/disable-feature` shortcuts

## Database Layers

### Primary: Firestore
- Document-based storage
- Collections per feature (`content_review_configs`, `content_review_submissions`, etc.)
- Repository pattern for data access

### Legacy: SQLAlchemy (`db/`)
- Originally planned for Albion data
- Currently unused - kept for potential future use
