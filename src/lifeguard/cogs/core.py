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
        view = _PurgeConfirmView()
        await interaction.response.send_message(
            "⚠️ **This will permanently delete ALL messages in this channel.**\n"
            "Are you sure?",
            view=view,
            ephemeral=True,
        )
        await view.wait()

        if not view.confirmed:
            return  # cancelled or timed out

        channel = interaction.channel
        if channel is None or not isinstance(channel, discord.TextChannel):
            await interaction.followup.send(
                "❌ This command can only be used in a guild text channel.",
                ephemeral=True,
            )
            return

        bot_member = channel.guild.me
        perms = channel.permissions_for(bot_member)
        if not perms.manage_messages:
            await interaction.followup.send(
                "❌ I lack **Manage Messages** permission in this channel.",
                ephemeral=True,
            )
            return

        try:
            deleted = await channel.purge(limit=None)
            await interaction.followup.send(
                f"🗑️ Deleted {len(deleted)} messages.", ephemeral=True,
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Permission denied — I can't delete messages here.",
                ephemeral=True,
            )
        except discord.HTTPException as exc:
            await interaction.followup.send(
                f"❌ Discord API error: {exc}",
                ephemeral=True,
            )
        except Exception as exc:
            await interaction.followup.send(
                f"❌ Unexpected error: {exc}",
                ephemeral=True,
            )


class _PurgeConfirmView(discord.ui.View):
    """Confirmation dialog for the /purge command."""

    def __init__(self) -> None:
        super().__init__(timeout=30)
        self.confirmed = False

    @discord.ui.button(label="Delete All Messages", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.confirmed = True
        await interaction.response.edit_message(content="Purging…", view=None)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(content="Purge cancelled.", view=None)
        self.stop()
