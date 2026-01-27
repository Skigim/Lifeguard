"""Albion Online Cog - Market prices and build commands."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from lifeguard.config import Config
from lifeguard.modules.albion.api import fetch_prices
from lifeguard.modules.albion import repo

if TYPE_CHECKING:
    from google.cloud.firestore import Client as FirestoreClient

LOGGER = logging.getLogger(__name__)


# --- Feature Check Decorators ---

class FeatureDisabledError(app_commands.CheckFailure):
    """Raised when a feature is disabled."""
    def __init__(self, feature_name: str):
        self.feature_name = feature_name
        super().__init__(f"{feature_name} is not enabled in this server.")


def require_albion_prices():
    """Check that Albion price lookup is enabled for this guild."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return False
        cog = interaction.client.get_cog("AlbionCog")
        if not cog or not cog.firestore:
            return False
        features = repo.get_guild_features(cog.firestore, interaction.guild.id)
        if not features or not features.albion_prices_enabled:
            raise FeatureDisabledError("Albion Price Lookup")
        return True
    return app_commands.check(predicate)


def require_albion_builds():
    """Check that Albion builds is enabled for this guild."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return False
        cog = interaction.client.get_cog("AlbionCog")
        if not cog or not cog.firestore:
            return False
        features = repo.get_guild_features(cog.firestore, interaction.guild.id)
        if not features or not features.albion_builds_enabled:
            raise FeatureDisabledError("Albion Builds")
        return True
    return app_commands.check(predicate)


# Gear slot keys for build display
SLOT_KEYS = [
    "head",
    "chest",
    "shoes",
    "main_hand",
    "off_hand",
    "cape",
    "bag",
    "mount",
    "food",
    "potion",
]


class AlbionCog(commands.Cog):
    """Albion Online game integrations."""

    def __init__(
        self, bot: commands.Bot, config: Config, session: aiohttp.ClientSession
    ) -> None:
        self.bot = bot
        self.config = config
        self.session = session

    @property
    def firestore(self) -> FirestoreClient | None:
        return getattr(self.bot, "lifeguard_firestore", None)

    async def cog_load(self) -> None:
        LOGGER.info("Albion cog loaded")

    @app_commands.command(
        name="price", description="Fetch current market prices (Albion Data Project)"
    )
    @app_commands.describe(
        item="Albion item id, e.g. T4_BAG or T8_POTION_HEAL",
        location="City name, e.g. Caerleon or Bridgewatch",
        quality="Item quality 1-5 (1=Normal, 5=Masterpiece)",
    )
    @require_albion_prices()
    async def price(
        self,
        interaction: discord.Interaction,
        item: str,
        location: str = "Caerleon",
        quality: int = 1,
    ) -> None:
        """Fetch market prices for an Albion item."""
        await interaction.response.defer(thinking=True, ephemeral=True)

        quality = max(1, min(5, quality))
        base_url = self.config.albion_data_base

        try:
            prices = await fetch_prices(
                self.session,
                base_url=base_url,
                items=[item.strip()],
                locations=[location.strip()],
                qualities=[quality],
            )
        except aiohttp.ClientResponseError as e:
            await interaction.followup.send(f"Albion Data API error: HTTP {e.status}")
            return
        except Exception as e:
            await interaction.followup.send(
                f"Failed to fetch prices: {type(e).__name__}"
            )
            return

        if not prices:
            await interaction.followup.send(
                "No data returned. Check item id / location / quality."
            )
            return

        p = prices[0]
        lines = [
            f"**{p.item_id}** @ **{p.city}** (Q{p.quality})",
            f"Sell min: **{p.sell_price_min:,}**",
            f"Buy max: **{p.buy_price_max:,}**",
            f"Source: {base_url}",
        ]
        await interaction.followup.send("\n".join(lines))

    @app_commands.command(name="build", description="Fetch a saved build by id")
    @app_commands.describe(build_id="Firestore document id from the dashboard")
    @require_albion_builds()
    async def build_slash(
        self, interaction: discord.Interaction, build_id: str
    ) -> None:
        """Fetch and display a saved Albion build."""
        if self.firestore is None:
            await interaction.response.send_message(
                "Backend is disabled. Set FIREBASE_ENABLED=true and restart the bot.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(thinking=True, ephemeral=False)

        data = repo.get_build(self.firestore, build_id)
        if data is None:
            await interaction.followup.send(f"Build not found: {build_id}")
            return

        def fmt_ts(value: object) -> str | None:
            if isinstance(value, datetime):
                return value.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
            return None

        player_name = data.get("player_name")
        guild_name = data.get("guild_name")
        zone_name = data.get("zone_name")
        created_at = fmt_ts(data.get("created_at"))

        lines: list[str] = []
        if player_name:
            lines.append(f"**Player:** {player_name}")
        if guild_name:
            lines.append(f"**Guild:** {guild_name}")
        if zone_name:
            lines.append(f"**Zone:** {zone_name}")
        if created_at:
            lines.append(f"**Created:** {created_at}")
        lines.append(f"**ID:** {build_id}")

        lines.append("")
        lines.append("**Gear:**")

        any_slot = False
        for key in SLOT_KEYS:
            slot = data.get(key)
            if not isinstance(slot, dict):
                continue
            item_id = slot.get("item_id")
            if not item_id:
                continue
            any_slot = True
            label = key.replace("_", " ").title()
            lines.append(f"- {label}: {item_id}")

        if not any_slot:
            lines.append("- (no gear saved)")

        await interaction.followup.send("\n".join(lines))

    # --- Error Handler ---

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        """Handle errors from app commands in this cog."""
        if isinstance(error, FeatureDisabledError):
            await interaction.response.send_message(
                f"❌ {error.feature_name} is not enabled in this server.\n"
                "An admin can enable it using `/enable-feature`.",
                ephemeral=True,
            )
            return
        # Re-raise other errors for global handler
        raise error


async def setup(bot: commands.Bot) -> None:
    """Setup function for loading as an extension."""
    # This requires config and session to be passed - use direct loading instead
    pass
