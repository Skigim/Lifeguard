"""Core commands."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from lifeguard.features import FEATURES

FEATURE_DOCS_URL = "https://github.com/Skigim/Lifeguard/blob/main/docs/features"


def format_latency(seconds: float) -> str:
    return f"Pong! {round(seconds * 1000)} ms"


class Core(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="ping", description="Check the bot's latency")
    async def ping(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(format_latency(self.bot.latency), ephemeral=True)

    @app_commands.command(name="help", description="Open the documentation for a bot feature")
    @app_commands.describe(feature="Choose the feature you want help with")
    async def help(self, interaction: discord.Interaction, feature: str) -> None:
        name = feature.strip().casefold()
        if name in FEATURES:
            message = f"[Open the {name} documentation]({FEATURE_DOCS_URL}/{name}.md)"
        else:
            message = "Unknown feature. Choose a feature from the `/help` suggestions."
        await interaction.response.send_message(message, ephemeral=True)

    @help.autocomplete("feature")
    async def help_features(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        matches = [name for name in sorted(FEATURES) if current.casefold() in name.casefold()]
        return [app_commands.Choice(name=name, value=name) for name in matches[:25]]


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Core(bot))
