from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from lifeguard.modules.voice_lobby import repo
from lifeguard.modules.voice_lobby.config import VoiceLobbyConfig

if TYPE_CHECKING:
    from google.cloud.firestore import Client as FirestoreClient

LOGGER = logging.getLogger(__name__)


@dataclass
class _LobbySession:
    guild_id: int
    owner_id: int
    voice_channel_id: int


class VoiceLobbyCog(commands.Cog):
    """Temporary voice lobbies created from an entry voice channel."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._sessions_by_voice_id: dict[int, _LobbySession] = {}

    async def cog_load(self) -> None:
        LOGGER.info("Voice Lobby cog loaded")

    @property
    def firestore(self) -> FirestoreClient:
        return self.bot.lifeguard_firestore  # type: ignore[attr-defined]

    @staticmethod
    def _sanitize_channel_name(name: str) -> str:
        normalized = " ".join(name.strip().split())
        if not normalized:
            return "Lobby"
        return normalized[:100]

    @staticmethod
    def _member_has_any_role(member: discord.Member, role_ids: list[int]) -> bool:
        if not role_ids:
            return False
        member_role_ids = {role.id for role in member.roles}
        return bool(member_role_ids & set(role_ids))

    def _can_create_lobby(self, member: discord.Member, config: VoiceLobbyConfig) -> bool:
        if not config.creator_role_ids:
            return True
        return self._member_has_any_role(member, config.creator_role_ids)

    def _can_join_lobby(
        self,
        member: discord.Member,
        owner_id: int,
        config: VoiceLobbyConfig,
    ) -> bool:
        if member.id == owner_id:
            return True
        if not config.join_role_ids:
            return True
        return self._member_has_any_role(member, config.join_role_ids)

    def _format_lobby_name(self, member: discord.Member, template: str) -> str:
        safe_template = template or "Lobby - {owner}"
        try:
            name = safe_template.format(
                owner=member.display_name,
                username=member.name,
            )
        except (KeyError, ValueError):
            name = f"Lobby - {member.display_name}"

        return self._sanitize_channel_name(name)

    def _find_session_by_owner(self, guild_id: int, owner_id: int) -> _LobbySession | None:
        for session in self._sessions_by_voice_id.values():
            if session.guild_id == guild_id and session.owner_id == owner_id:
                return session
        return None

    def _resolve_category(
        self,
        guild: discord.Guild,
        config: VoiceLobbyConfig,
        entry_channel: discord.VoiceChannel,
    ) -> discord.CategoryChannel | None:
        if config.lobby_category_id is not None:
            category = guild.get_channel(config.lobby_category_id)
            if isinstance(category, discord.CategoryChannel):
                return category
        return entry_channel.category

    @staticmethod
    def _build_voice_channel_overwrites(
        guild: discord.Guild,
        owner: discord.Member,
        join_roles: list[discord.Role],
    ) -> dict[discord.abc.Snowflake, discord.PermissionOverwrite]:
        bot_member = guild.me
        overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
            owner: discord.PermissionOverwrite(
                view_channel=True,
                connect=True,
                manage_channels=True,
                move_members=True,
                send_messages=True,
                read_message_history=True,
            ),
        }

        if join_roles:
            overwrites[guild.default_role] = discord.PermissionOverwrite(
                connect=False,
                send_messages=False,
                read_message_history=False,
            )
            for role in join_roles:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    connect=True,
                    send_messages=True,
                    read_message_history=True,
                )

        if bot_member is not None:
            overwrites[bot_member] = discord.PermissionOverwrite(
                view_channel=True,
                connect=True,
                manage_channels=True,
                move_members=True,
                send_messages=True,
                read_message_history=True,
            )

        return overwrites

    async def _create_lobby_for_member(
        self,
        member: discord.Member,
        entry_channel: discord.VoiceChannel,
    ) -> None:
        config = repo.get_or_create_config(self.firestore, member.guild.id)
        category = self._resolve_category(member.guild, config, entry_channel)
        lobby_name = self._format_lobby_name(member, config.name_template)
        join_roles = [
            role
            for role_id in config.join_role_ids
            if (role := member.guild.get_role(role_id)) is not None
        ]

        voice_channel = await member.guild.create_voice_channel(
            name=lobby_name,
            category=category,
            overwrites=self._build_voice_channel_overwrites(member.guild, member, join_roles),
            user_limit=max(0, min(config.default_user_limit, 99)),
            reason=f"Temporary lobby created for {member}",
        )

        self._sessions_by_voice_id[voice_channel.id] = _LobbySession(
            guild_id=member.guild.id,
            owner_id=member.id,
            voice_channel_id=voice_channel.id,
        )

        await member.move_to(voice_channel, reason="Moved into newly-created temporary lobby")

        from lifeguard.modules.voice_lobby.views.config_ui import LobbyConfigView

        await voice_channel.send(
            content=(
                f"{member.mention} your temporary lobby is ready.\n"
                "Use the controls below to change channel name, set user limit, or close the lobby."
            ),
            view=LobbyConfigView(self, voice_channel.id, member.id),
        )

    async def _cleanup_lobby_if_empty(self, voice_channel_id: int) -> None:
        session = self._sessions_by_voice_id.get(voice_channel_id)
        if session is None:
            return

        guild = self.bot.get_guild(session.guild_id)
        if guild is None:
            self._sessions_by_voice_id.pop(voice_channel_id, None)
            return

        voice_channel = guild.get_channel(session.voice_channel_id)
        if isinstance(voice_channel, discord.VoiceChannel) and voice_channel.members:
            return

        if isinstance(voice_channel, discord.VoiceChannel):
            try:
                await voice_channel.delete(reason="Temporary lobby cleaned up")
            except (discord.Forbidden, discord.HTTPException):
                LOGGER.exception("Failed deleting lobby voice channel %s", voice_channel.id)

        self._sessions_by_voice_id.pop(voice_channel_id, None)

    async def _get_lobby_voice_channel(self, guild: discord.Guild, voice_channel_id: int) -> discord.VoiceChannel | None:
        channel = guild.get_channel(voice_channel_id)
        if isinstance(channel, discord.VoiceChannel):
            return channel
        return None

    def _get_lobby_owner(self, voice_channel_id: int) -> int | None:
        session = self._sessions_by_voice_id.get(voice_channel_id)
        if session is None:
            return None
        return session.owner_id

    async def update_lobby_name(
        self,
        interaction: discord.Interaction,
        voice_channel_id: int,
        requested_name: str,
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return

        owner_id = self._get_lobby_owner(voice_channel_id)
        if owner_id is not None and owner_id != interaction.user.id:
            await interaction.response.send_message(
                "Only the lobby owner can perform this action.",
                ephemeral=True,
            )
            return

        channel = await self._get_lobby_voice_channel(interaction.guild, voice_channel_id)
        if channel is None:
            await interaction.response.send_message("Lobby channel no longer exists.", ephemeral=True)
            return

        safe_name = self._sanitize_channel_name(requested_name)
        await channel.edit(name=safe_name, reason=f"Lobby renamed by {interaction.user}")
        await interaction.response.send_message(f"Lobby renamed to **{safe_name}**.", ephemeral=True)

    async def update_lobby_user_limit(
        self,
        interaction: discord.Interaction,
        voice_channel_id: int,
        user_limit: int,
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return

        owner_id = self._get_lobby_owner(voice_channel_id)
        if owner_id is not None and owner_id != interaction.user.id:
            await interaction.response.send_message(
                "Only the lobby owner can perform this action.",
                ephemeral=True,
            )
            return

        if user_limit < 0 or user_limit > 99:
            await interaction.response.send_message(
                "User limit must be between 0 and 99.",
                ephemeral=True,
            )
            return

        channel = await self._get_lobby_voice_channel(interaction.guild, voice_channel_id)
        if channel is None:
            await interaction.response.send_message("Lobby channel no longer exists.", ephemeral=True)
            return

        await channel.edit(user_limit=user_limit, reason=f"Lobby limit updated by {interaction.user}")
        if user_limit == 0:
            await interaction.response.send_message("Lobby user limit removed.", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"Lobby user limit set to **{user_limit}**.",
                ephemeral=True,
            )

    async def close_lobby(self, interaction: discord.Interaction, voice_channel_id: int) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return

        owner_id = self._get_lobby_owner(voice_channel_id)
        if owner_id is not None and owner_id != interaction.user.id:
            await interaction.response.send_message(
                "Only the lobby owner can perform this action.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message("Closing lobby…", ephemeral=True)
        await self._force_cleanup_lobby(interaction.guild, voice_channel_id)

    async def _force_cleanup_lobby(self, guild: discord.Guild, voice_channel_id: int) -> None:
        session = self._sessions_by_voice_id.get(voice_channel_id)
        if session is None:
            return

        voice_channel = guild.get_channel(session.voice_channel_id)
        if isinstance(voice_channel, discord.VoiceChannel):
            try:
                await voice_channel.delete(reason="Temporary lobby closed by owner")
            except (discord.Forbidden, discord.HTTPException):
                LOGGER.exception("Failed deleting lobby voice channel %s", voice_channel.id)

        self._sessions_by_voice_id.pop(voice_channel_id, None)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.bot:
            return

        if before.channel is not None and before.channel.id in self._sessions_by_voice_id:
            if after.channel is None or after.channel.id != before.channel.id:
                await self._cleanup_lobby_if_empty(before.channel.id)

        if after.channel is None:
            return

        config = repo.get_config(self.firestore, member.guild.id)
        if config is None or not config.enabled or config.entry_voice_channel_id is None:
            return

        managed_session = self._sessions_by_voice_id.get(after.channel.id)
        if managed_session is not None:
            if before.channel is not None and before.channel.id == after.channel.id:
                return

            if not self._can_join_lobby(member, managed_session.owner_id, config):
                await member.move_to(
                    None,
                    reason="User does not match configured lobby join roles",
                )
            return

        if after.channel.id != config.entry_voice_channel_id:
            return

        if before.channel is not None and before.channel.id == after.channel.id:
            return

        if not self._can_create_lobby(member, config):
            await member.move_to(
                None,
                reason="User does not match configured lobby creator roles",
            )
            return

        active_lobby = self._find_session_by_owner(member.guild.id, member.id)
        if active_lobby is not None:
            channel = member.guild.get_channel(active_lobby.voice_channel_id)
            if isinstance(channel, discord.VoiceChannel):
                await member.move_to(channel, reason="Moved back to existing temporary lobby")
                return

            self._sessions_by_voice_id.pop(active_lobby.voice_channel_id, None)

        if not isinstance(after.channel, discord.VoiceChannel):
            return

        try:
            await self._create_lobby_for_member(member, after.channel)
        except (discord.Forbidden, discord.HTTPException):
            LOGGER.exception("Failed to create temporary lobby for member %s", member.id)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VoiceLobbyCog(bot))
