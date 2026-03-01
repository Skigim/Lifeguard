"""Modal for adding notes during review."""

from __future__ import annotations

from typing import Callable, Coroutine, Any

import discord


class NoteModal(discord.ui.Modal):
    """Modal for adding a note to a review category."""

    reference = discord.ui.TextInput(
        label="Reference",
        style=discord.TextStyle.short,
        placeholder="e.g., timestamp, section, or specific moment",
        required=False,
        max_length=100,
    )

    feedback = discord.ui.TextInput(
        label="Feedback",
        style=discord.TextStyle.paragraph,
        placeholder="Your detailed feedback for this category...",
        required=True,
        max_length=1024,
    )

    def __init__(
        self,
        category_name: str,
        on_submit_callback: Callable[
            [discord.Interaction, str, str], Coroutine[Any, Any, None]
        ],
        existing_reference: str = "",
        existing_feedback: str = "",
    ) -> None:
        super().__init__(title=f"Add Note: {category_name[:40]}")
        self.on_submit_callback = on_submit_callback

        # Pre-fill with existing values if editing
        if existing_reference:
            self.reference.default = existing_reference
        if existing_feedback:
            self.feedback.default = existing_feedback

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Handle note submission."""
        await self.on_submit_callback(
            interaction,
            self.reference.value.strip(),
            self.feedback.value.strip(),
        )
