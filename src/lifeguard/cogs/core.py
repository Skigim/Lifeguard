from __future__ import annotations

import re

import discord
from discord import app_commands
from discord.ext import commands


class CoreCog(commands.Cog):
    """Core bot commands."""

    purge_group = app_commands.Group(
        name="purge",
        description="Delete messages in this channel",
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="ping")
    async def ping_prefix(self, ctx: commands.Context) -> None:
        await ctx.reply("pong")

    @app_commands.command(name="ping", description="Health check")
    async def ping_slash(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message("pong", ephemeral=True)

    @purge_group.command(
        name="number", description="Delete a number of recent messages"
    )
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.describe(count="Number of recent messages to delete (1-1000)")
    async def purge_number(
        self,
        interaction: discord.Interaction,
        count: app_commands.Range[int, 1, 1000],
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        channel = await self._get_text_channel_for_purge(interaction)
        if channel is None:
            return

        await self._run_purge(interaction, channel, limit=count)

    @purge_group.command(
        name="until",
        description="Delete all messages posted after a message ID or link",
    )
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.describe(
        message_ref="Message ID or full message link to purge messages below"
    )
    async def purge_until(
        self,
        interaction: discord.Interaction,
        message_ref: str,
    ) -> None:
        message_id = _extract_message_id(message_ref)
        if message_id is None:
            await interaction.response.send_message(
                "❌ Please provide a valid message ID or Discord message link.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        channel = await self._get_text_channel_for_purge(interaction)
        if channel is None:
            return

        try:
            target_message = await channel.fetch_message(message_id)
        except discord.NotFound:
            await interaction.followup.send(
                "❌ I couldn't find that message in this channel.",
                ephemeral=True,
            )
            return
        except discord.HTTPException as exc:
            await interaction.followup.send(
                f"❌ Failed to fetch the target message: {exc}",
                ephemeral=True,
            )
            return

        await self._run_purge(interaction, channel, limit=None, after=target_message)

    @purge_group.command(
        name="full",
        description="Delete all messages in this channel",
    )
    @app_commands.default_permissions(manage_messages=True)
    async def purge_full(self, interaction: discord.Interaction) -> None:
        confirmed = await self._confirm_purge(
            interaction,
            "⚠️ **This will permanently delete ALL messages in this channel.**\n"
            "Are you sure?",
        )
        if not confirmed:
            return

        channel = await self._get_text_channel_for_purge(interaction)
        if channel is None:
            return

        await self._run_purge(interaction, channel, limit=None)

    async def _confirm_purge(
        self,
        interaction: discord.Interaction,
        prompt: str,
    ) -> bool:
        view = _PurgeConfirmView()
        await interaction.response.send_message(
            prompt,
            view=view,
            ephemeral=True,
        )
        await view.wait()
        return view.confirmed

    async def _get_text_channel_for_purge(
        self,
        interaction: discord.Interaction,
    ) -> discord.TextChannel | None:
        channel = interaction.channel
        if channel is None or not isinstance(channel, discord.TextChannel):
            await interaction.followup.send(
                "❌ This command can only be used in a guild text channel.",
                ephemeral=True,
            )
            return None

        bot_member = channel.guild.me
        if bot_member is None:
            await interaction.followup.send(
                "❌ I couldn't resolve my guild member permissions.",
                ephemeral=True,
            )
            return None

        perms = channel.permissions_for(bot_member)
        if not perms.manage_messages:
            await interaction.followup.send(
                "❌ I lack **Manage Messages** permission in this channel.",
                ephemeral=True,
            )
            return None

        return channel

    async def _run_purge(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        *,
        limit: int | None,
        after: discord.abc.Snowflake | None = None,
    ) -> None:
        try:
            deleted = await channel.purge(limit=limit, after=after)
            await interaction.followup.send(
                f"🗑️ Deleted {len(deleted)} messages.",
                ephemeral=True,
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


def _extract_message_id(message_ref: str) -> int | None:
    value = message_ref.strip()
    if value.isdigit():
        return int(value)

    match = re.search(r"discord(?:app)?\.com/channels/\d+/\d+/(\d+)", value)
    if match is None:
        return None
    return int(match.group(1))


class _PurgeConfirmView(discord.ui.View):
    """Confirmation dialog for the /purge command."""

    def __init__(self) -> None:
        super().__init__(timeout=30)
        self.confirmed = False

    @discord.ui.button(label="Delete All Messages", style=discord.ButtonStyle.danger)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.confirmed = True
        await interaction.response.edit_message(content="Purging…", view=None)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(content="Purge cancelled.", view=None)
        self.stop()
