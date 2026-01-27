from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class CoreCog(commands.Cog):
    """Core bot commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="ping")
    async def ping_prefix(self, ctx: commands.Context) -> None:
        await ctx.reply("pong")

    @app_commands.command(name="ping", description="Health check")
    async def ping_slash(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message("pong", ephemeral=True)

    @app_commands.command(name="purge", description="Delete all messages in this channel")
    @app_commands.default_permissions(manage_messages=True)
    async def purge(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=None)
        await interaction.followup.send(f"🗑️ Deleted {len(deleted)} messages.", ephemeral=True)
