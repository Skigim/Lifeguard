# Copilot Instructions for Lifeguard

## Project Overview
Lifeguard is a Discord bot built with discord.py, using Firebase/Firestore as the backend. It follows a modular architecture with feature modules under `src/lifeguard/modules/`.

## Key Patterns

### Module Structure
Each feature module in `modules/` follows this pattern:
```
modules/<name>/
├── __init__.py    # Public exports with __all__
├── cog.py         # Discord commands (Cog class)
├── models.py      # Dataclasses with to_firestore()/from_firestore()
├── repo.py        # Firestore CRUD operations
└── views/         # Optional: Discord UI components
```

### Code Style
- Always use `from __future__ import annotations` 
- Type hints with modern syntax: `str | None` not `Optional[str]`
- Logging: `LOGGER = logging.getLogger(__name__)`
- Shared utilities in `lifeguard/utils.py` and `lifeguard/exceptions.py`

### Firestore Models
```python
@dataclass
class MyModel:
    id: str
    # fields...
    
    def to_firestore(self) -> dict:
        return drop_none(asdict(self))
    
    @classmethod
    def from_firestore(cls, data: dict) -> MyModel:
        return cls(...)
```

### Feature Checks
Use `FeatureDisabledError` from `lifeguard.exceptions` for guild feature toggles.

### Bot Integration
Register new cogs in `bot.py` via `setup_hook()`.

## File Locations
- Config: `lifeguard/config.py` (env vars via dotenv)
- Entry point: `lifeguard/__main__.py`
- Core commands: `lifeguard/cogs/core.py`
- Feature modules: `lifeguard/modules/<name>/`
