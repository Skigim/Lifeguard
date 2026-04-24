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

All feature management still starts from the central `/config` command,
but `ConfigCog` should stay a thin router. Feature-specific config behavior
belongs in the feature cog, not in `cogs/config_cog.py` or
`cogs/config_views.py`.

Use this split of responsibilities:

1. `ConfigFeatureSelectView` exposes the feature entrypoint.
2. `ConfigCog` resolves the feature cog and delegates.
3. The feature cog owns status, enable, disable, setup, and custom config flows.
4. Feature-specific views stay under `modules/<name>/views/`.

#### a) Add the feature to the shared menu

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

#### b) Define a feature-facing interface when needed

If the shared shell needs to call feature-owned config operations, add or
implement a protocol in `lifeguard/feature_interfaces.py`.

```python
class SupportsConfigToggle(Protocol):
    async def show_config_status(
        self,
        interaction: discord.Interaction,
        *,
        view: discord.ui.View,
    ) -> None: ...

    async def enable_feature(
        self,
        interaction: discord.Interaction,
        *,
        use_send: bool = False,
    ) -> None: ...

    async def disable_feature(
        self,
        interaction: discord.Interaction,
        *,
        use_send: bool = False,
    ) -> None: ...
```

Define a feature-specific protocol instead when the module needs richer setup
or navigation hooks.

#### c) Keep `ConfigCog` focused on delegation

```python
async def _show_<name>_menu(self, interaction: discord.Interaction) -> None:
    feature_cog = self._get_<name>_cog()
    if feature_cog is None:
        await interaction.response.edit_message(
            content="<Name> module is not loaded.",
            embed=None,
            view=None,
        )
        return

    await feature_cog.show_config_menu(
        interaction,
        on_back_to_home=self._show_config_home,
    )

async def _show_<name>_status(self, interaction: discord.Interaction) -> None:
    feature_cog = self._get_<name>_cog()
    if feature_cog is None:
        await interaction.response.edit_message(
            content="<Name> module is not loaded.",
            embed=None,
            view=None,
        )
        return

    await feature_cog.show_config_status(
        interaction,
        view=<Name>ConfigView(
            feature_cog,
            on_back_to_home=self._show_config_home,
        ),
    )
```

`ConfigCog` can still own shared, generic views. It should not directly import a
feature repo or implement feature-specific persistence logic.

#### d) Keep feature UI inside the feature module

If the feature needs a custom sub-menu or nested views, keep them under
`modules/<name>/views/` and route back-navigation through callbacks or methods
provided by the feature cog.

```python
class <Name>ConfigView(discord.ui.View):
    def __init__(
        self,
        cog: "<Name>Cog",
        *,
        on_back_to_home: Callable[[discord.Interaction], Awaitable[None]],
    ) -> None:
        super().__init__(timeout=120)
        self.cog = cog
        self._on_back_to_home = on_back_to_home

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️")
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._on_back_to_home(interaction)
```

Feature views may call their own feature cog, but they should not resolve
`ConfigCog` or any other feature cog directly.

#### e) Register in the feature registry

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
