"""Toy feature used to exercise the enable/disable lifecycle end to end."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from lifeguard.core.process import Process


class Greeter(Process):
    """Keeps a counter so a restart (disable then enable) is visibly a fresh process."""

    name = "greeter"

    def __init__(self) -> None:
        self.greeted = 0

    async def start(self) -> None:
        self.greeted = 0

    async def stop(self) -> None:
        pass

    def greet(self, who: str) -> str:
        self.greeted += 1
        return f"Hello, {who}! (greeting #{self.greeted} since this feature started)"


class GreeterCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="greet", description="Say hello (needs the greeter feature)")
    @app_commands.guild_only()
    async def greet(self, interaction: discord.Interaction) -> None:
        assert interaction.guild_id is not None
        proc = self.bot.loader.require(Greeter.name, interaction.guild_id)  # type: ignore[attr-defined]
        assert isinstance(proc, Greeter)
        await interaction.response.send_message(proc.greet(interaction.user.display_name))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GreeterCog(bot))
