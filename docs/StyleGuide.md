# Code Style Guide

## Python Version
- Minimum: Python 3.11
- Use modern syntax features

## Imports

### Future Annotations
Always start files with:
```python
from __future__ import annotations
```

### Import Order
1. `__future__` imports
2. Standard library
3. Third-party packages
4. Local imports

```python
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from lifeguard.config import Config
from lifeguard.exceptions import FeatureDisabledError
```

### Type Checking Imports
Use `TYPE_CHECKING` for import-only types:
```python
if TYPE_CHECKING:
    from google.cloud.firestore import Client as FirestoreClient
```

## Type Hints

### Modern Union Syntax
```python
# ✅ Good
def get_user(id: int) -> User | None:
    ...

# ❌ Avoid
def get_user(id: int) -> Optional[User]:
    ...
```

### Return Type Annotations
Always annotate return types:
```python
def process(data: dict) -> list[str]:
    ...

async def fetch(url: str) -> bytes:
    ...
```

## Dataclasses

### Firestore Models
```python
@dataclass
class MyModel:
    id: str
    name: str
    optional_field: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_firestore(self) -> dict:
        return drop_none(asdict(self))

    @classmethod
    def from_firestore(cls, data: dict) -> MyModel:
        return cls(
            id=data["id"],
            name=data["name"],
            optional_field=data.get("optional_field"),
            created_at=data.get("created_at", datetime.now(timezone.utc)),
        )
```

### Frozen vs Mutable
- Use `@dataclass(frozen=True)` for immutable value objects
- Use plain `@dataclass` when mutation is needed

## Logging
```python
LOGGER = logging.getLogger(__name__)

# Usage
LOGGER.info("Processing %s", item_id)
LOGGER.exception("Failed to fetch data")  # Auto-includes traceback
```

## Discord Commands

### Slash Commands
```python
@app_commands.command(name="my-command", description="Brief description")
@app_commands.default_permissions(manage_messages=True)
async def my_command(self, interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    # ... do work
    await interaction.followup.send("Done!", ephemeral=True)
```

### Feature Checks
```python
@require_content_review()
@app_commands.command(name="submit", description="Submit content")
async def submit(self, interaction: discord.Interaction) -> None:
    ...
```

## Docstrings
Use docstrings for modules, classes, and complex functions:
```python
"""Content Review Cog - Slash commands and event handling."""

class ContentReviewCog(commands.Cog):
    """Handles content submission and review workflows."""
    
    def complex_method(self, data: dict) -> Result:
        """Process submission data and return result.
        
        Args:
            data: Raw submission fields
            
        Returns:
            Processed result with validation status
        """
```

## Formatting
- Use `ruff format` for consistent formatting
- Line length: default (88 characters)
- Use trailing commas in multi-line structures

## Code Quality Principles

### No Duplicate Logic
**Never duplicate logic.** If the same check, transformation, or behavior exists in multiple places, extract it to a single reusable function.

```python
# ❌ BAD: Duplicating feature check logic
@tz_group.command(name="set")
async def set_timezone(self, interaction):
    # Inline feature check - duplicated in every command
    config = repo.get_config(self.firestore, interaction.guild.id)
    if not config or not config.enabled:
        raise FeatureDisabledError("Time Impersonator")
    ...

@tz_group.command(name="clear")
async def clear_timezone(self, interaction):
    # Same check duplicated here
    config = repo.get_config(self.firestore, interaction.guild.id)
    if not config or not config.enabled:
        raise FeatureDisabledError("Time Impersonator")
    ...

# ✅ GOOD: Single predicate function used everywhere
async def _check_feature_enabled(interaction: discord.Interaction) -> bool:
    """Check that feature is enabled for this guild."""
    if not interaction.guild:
        return False
    cog = interaction.client.get_cog("MyCog")
    if not cog or not cog.firestore:
        return False
    config = repo.get_config(cog.firestore, interaction.guild.id)
    if not config or not config.enabled:
        raise FeatureDisabledError("Feature Name")
    return True

@tz_group.command(name="set")
@app_commands.check(_check_feature_enabled)
async def set_timezone(self, interaction):
    ...

@tz_group.command(name="clear")
@app_commands.check(_check_feature_enabled)
async def clear_timezone(self, interaction):
    ...
```

### No Lazy Shortcuts
Do not take shortcuts that create technical debt:

- **No copy-paste code** — Extract shared logic into functions
- **No wrapper functions that just call another function** — Use the underlying function directly
- **No inline implementations when a decorator/utility exists** — Use existing patterns
- **No "quick fixes" that duplicate existing solutions** — Find and extend the existing pattern

### Single Source of Truth
Every piece of logic should have exactly one canonical implementation:

- Feature checks → One predicate function per feature
- Validation logic → One validator function reused everywhere  
- Data transformations → One utility function in the appropriate module
- Error messages → Defined once, referenced by constant or function

### When Adding New Features
1. **Search first** — Check if similar logic already exists
2. **Extend, don't duplicate** — Add to existing patterns rather than creating parallel ones
3. **Refactor if needed** — If existing code doesn't support your use case, refactor it to be more general
