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
│   └── core.py          # Basic commands (ping, purge)
├── db/                   # SQLAlchemy layer (legacy/unused)
└── modules/              # Feature modules
    ├── albion/           # Albion Online integration
    └── content_review/   # Submission review system
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
- `DISCORD_TOKEN` - Bot authentication
- `GUILD_ID` - Optional dev guild for fast command sync
- `FIREBASE_*` - Firestore configuration

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

## Feature Flags
Guild-level feature toggles stored in Firestore:
- Checked via decorators (`@require_content_review()`)
- Raise `FeatureDisabledError` when disabled

## Database Layers

### Primary: Firestore
- Document-based storage
- Collections per feature (`content_review_configs`, `content_review_submissions`, etc.)
- Repository pattern for data access

### Legacy: SQLAlchemy (`db/`)
- Originally planned for Albion data
- Currently unused - kept for potential future use
