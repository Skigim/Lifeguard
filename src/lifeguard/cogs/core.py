"""Core commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from lifeguard.core.replies import reply

if TYPE_CHECKING:
    from lifeguard.bot import LifeguardBot

FEATURE_DOCS_URL = "https://github.com/Skigim/Lifeguard/blob/main/docs/features"


def format_latency(seconds: float) -> str:
    return f"Pong! {round(seconds * 1000)} ms"


class Core(commands.Cog):
    def __init__(self, bot: LifeguardBot) -> None:
        self.bot = bot

    @app_commands.command(name="ping", description="Check the bot's latency")
    async def ping(self, interaction: discord.Interaction) -> None:
        await reply(interaction, format_latency(self.bot.latency))

    @app_commands.command(name="help", description="Open the documentation for a bot feature")
    @app_commands.describe(feature="Choose the feature you want help with")
    async def help(self, interaction: discord.Interaction, feature: str) -> None:
        name = feature.strip().casefold()
        if name in self.bot.loader.names:
            message = f"[Open the {name} documentation]({FEATURE_DOCS_URL}/{name}.md)"
        else:
            message = "Unknown feature. Choose a feature from the `/help` suggestions."
        await reply(interaction, message)

    @help.autocomplete("feature")
    async def help_features(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        matches = [name for name in self.bot.loader.names if current.casefold() in name.casefold()]
        return [app_commands.Choice(name=name, value=name) for name in matches[:25]]


async def setup(bot: LifeguardBot) -> None:
    await bot.add_cog(Core(bot))
