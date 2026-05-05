# Module Development Guide

This guide explains how to create a new feature module for Lifeguard.

## Quick Start

1. Create the module folder: `src/lifeguard/modules/<name>/`
2. Add the required files (see structure below)
3. Add a `manifest.py` file that exports `FEATURE_MANIFEST`

## Module Structure

```
modules/<name>/
├── __init__.py         # Exports
├── manifest.py         # Feature registry metadata
├── cog.py              # Discord commands
├── models.py           # Data models
├── repo.py             # Firestore operations
├── config.py           # Module settings (optional)
├── config_adapter.py   # Shared-shell adapter (optional for toggleable features)
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

### 5. Register through `manifest.py`

Modules are discovered automatically. Export a `FEATURE_MANIFEST` instead of
editing `bot.py` or `ConfigCog`.

```python
from lifeguard.features.contracts import FeatureManifest
from lifeguard.modules.<name>.cog import <Name>Cog


FEATURE_MANIFEST = FeatureManifest(
    feature_key="<name>",
    display_name="<Name>",
    description="Brief description",
    emoji="🔧",
    requires_setup=False,
    cog_name="<Name>Cog",
    load_cog=lambda bot: <Name>Cog(bot),
    build_adapter=lambda bot: <Name>ConfigAdapter(bot),
)
```

## Optional: Feature Flags

If your module should be toggleable per-guild, you need:

1. A feature config model and repo CRUD
2. A feature check decorator to guard your commands
3. A config sub-menu wired into the central `/config` command

## Shared Forms Engine

Use `lifeguard.features.forms` when a module needs configurable submission fields,
category-based forms, or a guided response flow. The shared package owns the reusable
schema (`FormField`, `FormCategory`), validation, wizard flow, and persisted response
sessions so modules do not need to rebuild that infrastructure.

Keep module-specific publish and follow-up behavior inside the module package. A module
can translate shared form responses into embeds, tickets, review records, or any other
feature-specific output, but that publish logic should stay local rather than moving
into the shared forms engine.

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
but `ConfigCog` stays a thin registry-backed router. Feature-specific config
behavior belongs in the feature module, not in `cogs/config_cog.py` or
`cogs/config_views.py`.

Use this split of responsibilities:

1. `ConfigHomeView` renders discovered feature entries from the registry.
2. `ConfigCog` resolves a feature adapter from `bot.lifeguard_features` and delegates.
3. The feature adapter translates shared-shell actions into module-owned flows.
4. The feature cog owns status, enable, disable, setup, and custom config flows.
5. Feature-specific views stay under `modules/<name>/views/`.

#### a) Implement a shared-shell adapter

If the feature participates in `/config`, implement the `FeatureConfigAdapter`
contract from `lifeguard.features.contracts`.

```python
class <Name>ConfigAdapter:
    async def show_menu(
        self,
        interaction: discord.Interaction,
        *,
        on_back_to_home: Callable[[discord.Interaction], Awaitable[None]],
    ) -> None: ...

    async def show_status(
        self,
        interaction: discord.Interaction,
        *,
        on_back_to_home: Callable[[discord.Interaction], Awaitable[None]],
    ) -> None: ...

    async def enable(
        self,
        interaction: discord.Interaction,
        *,
        on_back_to_home: Callable[[discord.Interaction], Awaitable[None]] | None = None,
        use_send: bool = False,
    ) -> None: ...

    async def disable(
        self,
        interaction: discord.Interaction,
        *,
        use_send: bool = False,
    ) -> None: ...
```

#### b) Keep `ConfigCog` focused on delegation

```python
async def _dispatch_feature_menu(self, interaction: discord.Interaction, feature_key: str) -> None:
    manifest = self.feature_registry.get_manifest(feature_key)
    adapter = self.feature_registry.build_adapter(self.bot, feature_key)
    if manifest is None or adapter is None:
        await interaction.response.edit_message(
            content=f"{feature_key.replace('_', ' ').title()} is not currently installed.",
            embed=None,
            view=None,
        )
        return

    await adapter.show_menu(interaction, on_back_to_home=self._show_config_home)
```

`ConfigCog` can still own shared, generic views. It should not directly import a
feature repo or implement feature-specific persistence logic.

#### c) Keep feature UI inside the feature module

If the feature needs a custom sub-menu or nested views, keep them under
`modules/<name>/views/` and route back-navigation through callbacks or methods
provided by the feature cog.

```python
class <Name>ConfigView(discord.ui.View):
    def __init__(
        self,
        adapter: "<Name>ConfigAdapter",
        *,
        on_back_to_home: Callable[[discord.Interaction], Awaitable[None]],
    ) -> None:
        super().__init__(timeout=120)
        self.adapter = adapter
        self._on_back_to_home = on_back_to_home

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="↩️")
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._on_back_to_home(interaction)
```

Feature views may call their own feature adapter or feature cog, but they should
not resolve `ConfigCog` or any other feature directly.

#### d) Keep `__init__.py` lightweight

Discovery imports `manifest.py` directly. Keep `modules/<name>/__init__.py`
lightweight and avoid importing cogs, repos, or any heavy initialization there.

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
4. Verify manifest discovery: `python -m unittest discover -s tests -p 'test_module_manifests.py' -v`
