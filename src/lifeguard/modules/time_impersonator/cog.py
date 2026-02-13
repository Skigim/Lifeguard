from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo, available_timezones

import discord
from discord import app_commands
from discord.ext import commands

from lifeguard.exceptions import FeatureDisabledError
from lifeguard.modules.time_impersonator import repo
from lifeguard.modules.time_impersonator.models import UserTimezone

if TYPE_CHECKING:
    from google.cloud.firestore import Client as FirestoreClient

LOGGER = logging.getLogger(__name__)

_MSG_DB_UNAVAILABLE = "Database not available."

# Cache available timezones for autocomplete
_TIMEZONES: list[str] = sorted(available_timezones())

# Common timezones to prioritize in autocomplete
_COMMON_TIMEZONES = [
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/Toronto",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "Europe/Amsterdam",
    "Asia/Tokyo",
    "Asia/Shanghai",
    "Asia/Singapore",
    "Australia/Sydney",
    "Pacific/Auckland",
    "UTC",
]

# Webhook name used by this module
WEBHOOK_NAME = "LifeguardImpersonator"


async def timezone_autocomplete(  # NOSONAR - discord.py requires async
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    """Autocomplete handler for timezone parameter."""
    current_lower = current.lower()

    if not current:
        # Show common timezones when no input
        return [
            app_commands.Choice(name=tz, value=tz) for tz in _COMMON_TIMEZONES[:25]
        ]

    # Filter and prioritize matches
    matches: list[str] = []

    # First, add common timezones that match
    for tz in _COMMON_TIMEZONES:
        if current_lower in tz.lower():
            matches.append(tz)

    # Then add other matches
    for tz in _TIMEZONES:
        if tz not in matches and current_lower in tz.lower():
            matches.append(tz)
            if len(matches) >= 25:
                break

    return [app_commands.Choice(name=tz, value=tz) for tz in matches[:25]]


def _parse_and_replace_times(message: str, user_tz: ZoneInfo) -> str:
    """
    Parse natural language time references and replace with Discord timestamps.

    Args:
        message: The user's message text.
        user_tz: The user's timezone for reference.

    Returns:
        The message with time references replaced by Discord timestamp syntax.
    """
    # Import here to avoid import errors if dateparser not installed
    import dateparser  # type: ignore[import-not-found]
    from dateparser.search import search_dates  # type: ignore[import-not-found]

    # Get current time in user's timezone as reference
    now_in_user_tz = datetime.now(user_tz)

    # Common settings for parsing
    parse_settings = {
        "PREFER_DATES_FROM": "future",
        "RELATIVE_BASE": now_in_user_tz.replace(tzinfo=None),
        "TIMEZONE": str(user_tz),
        "RETURN_AS_TIMEZONE_AWARE": True,
    }

    # Search for date/time references
    # Use languages=['en'] to avoid false positives like "do" being parsed as
    # Portuguese/Spanish "domingo" (Sunday)
    results = search_dates(
        message,
        languages=["en"],
        settings=parse_settings,
    )

    if not results:
        return message

    # Sort by position in reverse order to replace from end to start
    # This prevents index shifting issues
    replacements: list[tuple[int, int, str]] = []

    # Punctuation that can trail time expressions and confuse the parser
    trailing_punct = "?!.,;:)"

    # Prepositions that dateparser includes but shouldn't be replaced
    # e.g., "at 8pm" should become "at <timestamp>" not "<timestamp>"
    leading_prepositions = ("at ", "by ", "from ", "until ", "till ", "around ")

    search_offset = 0

    for matched_text, _ in results:
        # Strip trailing punctuation that dateparser incorrectly includes
        clean_match = matched_text.rstrip(trailing_punct)
        if not clean_match:
            continue

        # Strip leading prepositions - keep them in the message
        time_only = clean_match
        for prep in leading_prepositions:
            if clean_match.lower().startswith(prep):
                time_only = clean_match[len(prep) :]
                break

        # Find the position of the time portion in the message
        # Search from search_offset so duplicate strings resolve to successive occurrences
        full_start_idx = message.find(clean_match, search_offset)
        if full_start_idx == -1:
            continue

        # Calculate the actual start position (after preposition)
        start_idx = full_start_idx + (len(clean_match) - len(time_only))

        # Advance offset past this match for the next iteration
        search_offset = full_start_idx + len(clean_match)

        # Re-parse the clean match using dateparser.parse() which handles times
        # correctly (search_dates has a bug where "7am" is parsed as July)
        reparsed_dt = dateparser.parse(
            clean_match, languages=["en"], settings=parse_settings
        )
        if not reparsed_dt:
            continue

        # Convert to Unix timestamp
        unix_ts = int(reparsed_dt.timestamp())

        # Create Discord timestamp (short time format)
        discord_ts = f"<t:{unix_ts}:t>"

        # Only replace the time portion, leaving preposition intact
        replacements.append((start_idx, len(time_only), discord_ts))

    # Sort by start index descending to replace from end first
    replacements.sort(key=lambda x: x[0], reverse=True)

    # Apply replacements
    result = message
    for start_idx, length, replacement in replacements:
        result = result[:start_idx] + replacement + result[start_idx + length :]

    return result


async def _get_or_create_webhook(
    channel: discord.TextChannel,
    bot_user: discord.User | discord.ClientUser,
) -> discord.Webhook:
    """
    Get an existing bot-owned webhook or create a new one.

    Args:
        channel: The text channel to get/create webhook in.
        bot_user: The bot's user object to identify owned webhooks.

    Returns:
        A webhook for impersonation.
    """
    webhooks = await channel.webhooks()

    # Look for existing bot-owned webhook
    for webhook in webhooks:
        if webhook.user and webhook.user.id == bot_user.id and webhook.name == WEBHOOK_NAME:
            return webhook

    # Create new webhook
    return await channel.create_webhook(name=WEBHOOK_NAME)


# --- Feature Check ---


async def _check_time_impersonator_enabled(interaction: discord.Interaction) -> bool:  # NOSONAR
    """Check that time impersonator is enabled for this guild."""
    if not interaction.guild:
        return False
    cog = interaction.client.get_cog("TimeImpersonatorCog")
    if not cog or not cog.firestore:
        return False
    config = repo.get_config(cog.firestore, interaction.guild.id)
    if not config or not config.enabled:
        raise FeatureDisabledError("Time Impersonator")
    return True


def require_time_impersonator():
    """Decorator to check that time impersonator is enabled for this guild."""
    return app_commands.check(_check_time_impersonator_enabled)


class TimeImpersonatorCog(commands.Cog):
    """Time Impersonator module commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        """Called when the cog is loaded."""
        LOGGER.info("Time Impersonator cog loaded")

    @property
    def firestore(self) -> FirestoreClient | None:
        """Access Firestore client from bot instance."""
        return getattr(self.bot, "lifeguard_firestore", None)

    # --- User Commands ---

    tz_group = app_commands.Group(name="tz", description="Timezone commands")

    @tz_group.command(name="set", description="Set your timezone for time parsing")
    @app_commands.describe(timezone="Your timezone (e.g., America/New_York)")
    @app_commands.autocomplete(timezone=timezone_autocomplete)
    @app_commands.check(_check_time_impersonator_enabled)
    async def set_timezone(
        self,
        interaction: discord.Interaction,
        timezone: str,
    ) -> None:
        """Set the user's preferred timezone."""
        if not self.firestore:
            await interaction.response.send_message(
                _MSG_DB_UNAVAILABLE, ephemeral=True
            )
            return

        # Validate timezone
        if timezone not in _TIMEZONES:
            await interaction.response.send_message(
                f"Invalid timezone: `{timezone}`. Please select from the autocomplete suggestions.",
                ephemeral=True,
            )
            return

        # Save to Firestore
        user_tz = UserTimezone(user_id=interaction.user.id, timezone=timezone)
        repo.save_user_timezone(self.firestore, user_tz)

        await interaction.response.send_message(
            f"Timezone set to **{timezone}**.", ephemeral=True, delete_after=5
        )

    @tz_group.command(name="clear", description="Clear your saved timezone")
    @app_commands.check(_check_time_impersonator_enabled)
    async def clear_timezone(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """Clear the user's saved timezone."""
        if not self.firestore:
            await interaction.response.send_message(
                _MSG_DB_UNAVAILABLE, ephemeral=True
            )
            return

        repo.delete_user_timezone(self.firestore, interaction.user.id)
        await interaction.response.send_message(
            "Timezone cleared.", ephemeral=True, delete_after=5
        )

    @require_time_impersonator()
    @app_commands.command(
        name="time",
        description="Send a message with time references converted to Discord timestamps",
    )
    @app_commands.describe(message="Your message with time references (e.g., 'Raid starts at 8pm')")
    async def send_time_message(
        self,
        interaction: discord.Interaction,
        message: str,
    ) -> None:
        """Send a message with natural language times converted to Discord timestamps."""
        if not self.firestore:
            await interaction.response.send_message(
                _MSG_DB_UNAVAILABLE, ephemeral=True
            )
            return

        # Check if in a guild text channel
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(
                "This command can only be used in a server text channel.",
                ephemeral=True,
            )
            return

        # Check bot permissions
        bot_member = interaction.guild.me
        if not interaction.channel.permissions_for(bot_member).manage_webhooks:
            await interaction.response.send_message(
                "I need the **Manage Webhooks** permission to use this command.",
                ephemeral=True,
            )
            return

        # Get user's timezone
        user_tz_record = repo.get_user_timezone(self.firestore, interaction.user.id)
        if not user_tz_record:
            await interaction.response.send_message(
                "Please set your timezone first using `/tz set`.", ephemeral=True
            )
            return

        # Defer response while processing
        await interaction.response.defer(ephemeral=True)

        try:
            # Parse and replace times
            user_tz = ZoneInfo(user_tz_record.timezone)
            formatted_message = _parse_and_replace_times(message, user_tz)
            LOGGER.debug(
                "Time parsing: input_len=%d, timezone=%s, output_len=%d",
                len(message),
                user_tz,
                len(formatted_message),
            )

            # Get or create webhook
            webhook = await _get_or_create_webhook(interaction.channel, self.bot.user)

            # Send message as user
            await webhook.send(
                content=formatted_message,
                username=interaction.user.display_name,
                avatar_url=interaction.user.display_avatar.url,
            )

            await interaction.followup.send("Message sent!", ephemeral=True)

        except Exception:
            LOGGER.exception("Failed to send time message")
            await interaction.followup.send(
                "Failed to send message. Please try again.", ephemeral=True
            )
