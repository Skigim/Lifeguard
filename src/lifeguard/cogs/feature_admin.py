"""Admin commands to enable and disable features per guild."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from lifeguard.core.loader import Loader


def render_feature_list(loader: Loader, guild_id: int) -> str:
    lines = []
    for name in loader.names:
        flag = "on" if loader.is_enabled(name, guild_id) else "off"
        lines.append(f"`{name}`: {flag} (process {loader.state(name).value})")
    return "\n".join(lines) or "No features registered."


@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
class FeatureAdmin(
    commands.GroupCog,
    group_name="feature",
    group_description="Enable or disable bot features",
):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @property
    def loader(self) -> Loader:
        return self.bot.loader  # type: ignore[attr-defined]

    async def _names(self, interaction: discord.Interaction, current: str):
        return [
            app_commands.Choice(name=n, value=n)
            for n in self.loader.names
            if current.lower() in n.lower()
        ]

    @app_commands.command(name="enable", description="Enable a feature on this server")
    async def enable(self, interaction: discord.Interaction, name: str) -> None:
        assert interaction.guild_id is not None
        if name not in self.loader.names:
            await interaction.response.send_message(f"Unknown feature `{name}`.", ephemeral=True)
            return
        await self.loader.enable(name, interaction.guild_id)
        await interaction.response.send_message(f"Enabled `{name}`.", ephemeral=True)

    @app_commands.command(name="disable", description="Disable a feature on this server")
    async def disable(self, interaction: discord.Interaction, name: str) -> None:
        assert interaction.guild_id is not None
        if name not in self.loader.names:
            await interaction.response.send_message(f"Unknown feature `{name}`.", ephemeral=True)
            return
        await self.loader.disable(name, interaction.guild_id)
        await interaction.response.send_message(f"Disabled `{name}`.", ephemeral=True)

    @app_commands.command(name="list", description="Show features and their state")
    async def list_features(self, interaction: discord.Interaction) -> None:
        assert interaction.guild_id is not None
        await interaction.response.send_message(
            render_feature_list(self.loader, interaction.guild_id), ephemeral=True
        )

    enable.autocomplete("name")(_names)
    disable.autocomplete("name")(_names)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(FeatureAdmin(bot))
