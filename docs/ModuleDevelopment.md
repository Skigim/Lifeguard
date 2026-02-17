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

    async def cog_load(self) -> None:
        """Called when the cog is loaded."""
        LOGGER.info("<Name> cog loaded")

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

If your module should be toggleable per-guild, you need:

1. A feature config model and repo CRUD
2. A feature check decorator to guard your commands
3. A config sub-menu wired into the central `/config` command

### 1. Create a Config Model

In your module's `config.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class <Name>Config:
    """Guild-level configuration for the <Name> module."""

    guild_id: int
    enabled: bool = False

    def to_firestore(self) -> dict:
        return {
            "guild_id": self.guild_id,
            "enabled": self.enabled,
        }

    @classmethod
    def from_firestore(cls, data: dict) -> <Name>Config:
        return cls(
            guild_id=data["guild_id"],
            enabled=data.get("enabled", False),
        )
```

### 2. Add Config CRUD to `repo.py`

```python
from lifeguard.modules.<name>.config import <Name>Config

CONFIGS_COLLECTION = "<name>_configs"


def get_config(firestore: FirestoreClient, guild_id: int) -> <Name>Config | None:
    doc = firestore.collection(CONFIGS_COLLECTION).document(str(guild_id)).get()
    if not doc.exists:
        return None
    return <Name>Config.from_firestore(doc.to_dict())


def save_config(firestore: FirestoreClient, config: <Name>Config) -> None:
    firestore.collection(CONFIGS_COLLECTION).document(str(config.guild_id)).set(
        config.to_firestore(), merge=True
    )
```

### 3. Add Feature Check Decorator

In your `cog.py`:

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

### 4. Apply to Commands

```python
@require_<name>()
@app_commands.command(name="my-command", description="Does something")
async def my_command(self, interaction: discord.Interaction) -> None:
    ...
```

### 5. Wiring into the Config Menu

All feature management flows through the central `/config` command
(hosted in `ConfigCog` at `cogs/config_cog.py`). Every module gets its own sub-menu
so users can enable, disable, and configure the feature from one place.

#### a) Create a config sub-menu view

Add your view to `cogs/config_views.py`:

```python
class <Name>ConfigView(discord.ui.View):
    """Config sub-menu for <Name> feature."""

    def __init__(self, cog: "ConfigCog") -> None:
        super().__init__(timeout=120)
        self.cog = cog

    @discord.ui.button(label="Status", style=discord.ButtonStyle.secondary, emoji="📋", row=0)
    async def status_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_<name>_status(interaction)

    @discord.ui.button(label="Enable", style=discord.ButtonStyle.success, emoji="✅", row=0)
    async def enable_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._enable_<name>(interaction)

    @discord.ui.button(label="Disable", style=discord.ButtonStyle.danger, emoji="❌", row=0)
    async def disable_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._disable_<name>(interaction)

    # Add more buttons for module-specific settings as needed

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️", row=1)
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog._show_config_home(interaction)
```

#### b) Add a button to `ConfigFeatureSelectView`

```python
@discord.ui.button(
    label="<Name>",
    style=discord.ButtonStyle.secondary,
    emoji="🔧",
    row=<row>,
)
async def <name>_button(
    self, interaction: discord.Interaction, button: discord.ui.Button
) -> None:
    await self.cog._show_<name>_menu(interaction)
```

#### c) Add cog helper methods to `ConfigCog`

```python
async def _show_<name>_menu(self, interaction: discord.Interaction) -> None:
    from lifeguard.cogs.config_views import <Name>ConfigView

    embed = discord.Embed(
        title="🔧 <Name> Config",
        description="Configure the <Name> feature.",
        color=discord.Color.blue(),
    )
    await interaction.response.edit_message(
        embed=embed, view=<Name>ConfigView(self), content=None
    )

async def _show_<name>_status(self, interaction: discord.Interaction) -> None:
    if not interaction.guild:
        return
    from lifeguard.modules.<name> import repo as <name>_repo
    from lifeguard.cogs.config_views import <Name>ConfigView

    config = <name>_repo.get_config(self.firestore, interaction.guild.id)
    status = "✅ Enabled" if config and config.enabled else "❌ Disabled"
    await interaction.response.edit_message(
        content=f"**<Name>:** {status}", embed=None, view=<Name>ConfigView(self)
    )

async def _enable_<name>(
    self, interaction: discord.Interaction, *, use_send: bool = False
) -> None:
    if not interaction.guild:
        return
    from lifeguard.modules.<name> import repo as <name>_repo
    from lifeguard.modules.<name>.config import <Name>Config

    config = <Name>Config(guild_id=interaction.guild.id, enabled=True)
    <name>_repo.save_config(self.firestore, config)
    await self._respond(interaction, "✅ **<Name> enabled!**", use_send=use_send)

async def _disable_<name>(
    self, interaction: discord.Interaction, *, use_send: bool = False
) -> None:
    if not interaction.guild:
        return
    from lifeguard.modules.<name> import repo as <name>_repo
    from lifeguard.modules.<name>.config import <Name>Config

    config = <name>_repo.get_config(self.firestore, interaction.guild.id)
    if not config or not config.enabled:
        await self._respond(interaction, "<Name> is not enabled.", use_send=use_send)
        return
    config = <Name>Config(guild_id=interaction.guild.id, enabled=False)
    <name>_repo.save_config(self.firestore, config)
    await self._respond(interaction, "✅ **<Name> disabled!**", use_send=use_send)
```

#### d) Register in the feature registry

Add your feature to the `FEATURES` list in `cogs/config_cog.py` so `enable-feature`
and `disable-feature` autocomplete picks it up:

```python
FEATURES: list[tuple[str, str, str, bool]] = [
    # ... existing ...
    ("<name>", "<Name>", "Brief description", False),
]
```

Then add the corresponding `elif` branches in `enable_feature_command`
and `disable_feature_command`.

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
