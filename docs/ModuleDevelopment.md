# Module Development Guide

This guide explains how to create a new feature module for Lifeguard.

## Quick Start

1. Create the module folder: `src/lifeguard/modules/<name>/`
2. Add the required files (see structure below)
3. Register the cog in `bot.py`

## Module Structure

```
modules/<name>/
├── __init__.py         # Exports
├── cog.py              # Discord commands
├── models.py           # Data models
├── repo.py             # Firestore operations
├── config.py           # Module settings (optional)
└── views/              # UI components (optional)
    ├── __init__.py
    └── my_modal.py
```

## Step-by-Step

### 1. Create `__init__.py`

Export public symbols:

```python
# <name> Module
# Brief description of what this module does

from lifeguard.modules.<name>.models import MyModel, OtherModel

__all__ = [
    "MyModel",
    "OtherModel",
]
```

### 2. Create `models.py`

Define your data structures:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from lifeguard.utils import drop_none


@dataclass
class MyModel:
    """Description of what this model represents."""
    
    id: str
    guild_id: int
    name: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_firestore(self) -> dict:
        return {
            "id": self.id,
            "guild_id": self.guild_id,
            "name": self.name,
            "created_at": self.created_at,
        }

    @classmethod
    def from_firestore(cls, data: dict) -> MyModel:
        return cls(
            id=data["id"],
            guild_id=data["guild_id"],
            name=data["name"],
            created_at=data.get("created_at", datetime.now(timezone.utc)),
        )
```

### 3. Create `repo.py`

Implement Firestore operations:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from lifeguard.modules.<name>.models import MyModel

if TYPE_CHECKING:
    from google.cloud.firestore import Client as FirestoreClient


COLLECTION = "<name>_items"


def get_item(firestore: FirestoreClient, item_id: str) -> MyModel | None:
    """Get an item by ID."""
    doc = firestore.collection(COLLECTION).document(item_id).get()
    if not doc.exists:
        return None
    return MyModel.from_firestore(doc.to_dict())


def save_item(firestore: FirestoreClient, item: MyModel) -> None:
    """Save or update an item."""
    firestore.collection(COLLECTION).document(item.id).set(
        item.to_firestore(), merge=True
    )


def delete_item(firestore: FirestoreClient, item_id: str) -> None:
    """Delete an item."""
    firestore.collection(COLLECTION).document(item_id).delete()
```

### 4. Create `cog.py`

Implement Discord commands:

```python
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from lifeguard.modules.<name> import repo

if TYPE_CHECKING:
    from google.cloud.firestore import Client as FirestoreClient

LOGGER = logging.getLogger(__name__)


class <Name>Cog(commands.Cog):
    """<Name> module commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @property
    def firestore(self) -> FirestoreClient | None:
        return getattr(self.bot, "lifeguard_firestore", None)

    @app_commands.command(name="my-command", description="Does something")
    async def my_command(self, interaction: discord.Interaction) -> None:
        if not self.firestore:
            await interaction.response.send_message(
                "Database not available.", ephemeral=True
            )
            return
        
        # Your logic here
        await interaction.response.send_message("Done!", ephemeral=True)
```

### 5. Register in `bot.py`

Add loader function and register in `setup_hook`:

```python
# At module level
def _load_<name>_cog(bot: commands.Bot) -> <Name>Cog:
    from lifeguard.modules.<name>.cog import <Name>Cog
    return <Name>Cog(bot)


# In setup_hook
@bot.event
async def setup_hook() -> None:
    # ... existing setup ...
    await bot.add_cog(_load_<name>_cog(bot))
```

## Optional: Feature Flags

If your module should be toggleable per-guild:

### 1. Add feature check decorator

```python
from lifeguard.exceptions import FeatureDisabledError


def require_<name>():
    """Check that <name> is enabled for this guild."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return False
        cog = interaction.client.get_cog("<Name>Cog")
        if not cog or not cog.firestore:
            return False
        config = repo.get_config(cog.firestore, interaction.guild.id)
        if not config or not config.enabled:
            raise FeatureDisabledError("<Name>")
        return True
    return app_commands.check(predicate)
```

### 2. Apply to commands

```python
@require_<name>()
@app_commands.command(name="my-command", description="Does something")
async def my_command(self, interaction: discord.Interaction) -> None:
    ...
```

## Optional: Discord UI Components

For modals, buttons, or select menus, create a `views/` folder:

```python
# views/my_modal.py
import discord


class MyModal(discord.ui.Modal, title="Submit"):
    name = discord.ui.TextInput(label="Name", required=True)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            f"Received: {self.name.value}", ephemeral=True
        )
```

## Testing Your Module

1. Set `FIREBASE_ENABLED=true` in `.env`
2. Run the bot: `python -m lifeguard`
3. Test commands in your dev guild
