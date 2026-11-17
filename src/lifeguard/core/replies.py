"""Send temporary private replies to Discord interactions."""

import discord

REPLY_TTL = 30


async def reply(
    interaction: discord.Interaction, text: str, *, view: discord.ui.View | None = None
) -> None:
    delay = view.timeout if view is not None and view.timeout is not None else REPLY_TTL
    options = {"view": view} if view is not None else {}
    if not interaction.response.is_done():
        await interaction.response.send_message(
            text, ephemeral=True, delete_after=delay, **options
        )
        return
    if interaction.response.type is discord.InteractionResponseType.deferred_channel_message:
        message = await interaction.edit_original_response(content=text, **options)
    else:
        message = await interaction.followup.send(text, ephemeral=True, wait=True, **options)
    await message.delete(delay=delay)
