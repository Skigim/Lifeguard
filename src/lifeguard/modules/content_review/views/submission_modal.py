"""Dynamic submission modal generated from config."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Callable, Coroutine, Any

import discord

if TYPE_CHECKING:
    from lifeguard.modules.content_review.config import ContentReviewConfig, SubmissionField


class SubmissionModal(discord.ui.Modal):
    """Dynamically generated submission modal based on config fields."""

    def __init__(
        self,
        config: ContentReviewConfig,
        on_submit_callback: Callable[[discord.Interaction, dict[str, str]], Coroutine[Any, Any, None]],
    ) -> None:
        super().__init__(title=config.modal_title)
        self.config = config
        self.on_submit_callback = on_submit_callback
        self._field_inputs: dict[str, discord.ui.TextInput] = {}

        # Add fields from config (max 5 due to Discord modal limits)
        for field_config in config.submission_fields[:5]:
            text_input = self._create_text_input(field_config)
            self._field_inputs[field_config.id] = text_input
            self.add_item(text_input)

    def _create_text_input(self, field_config: SubmissionField) -> discord.ui.TextInput:
        """Create a TextInput from a SubmissionField config."""
        style = (
            discord.TextStyle.paragraph
            if field_config.field_type == "paragraph"
            else discord.TextStyle.short
        )

        return discord.ui.TextInput(
            label=field_config.label,
            style=style,
            placeholder=field_config.placeholder or None,
            required=field_config.required,
            max_length=1024 if field_config.field_type == "paragraph" else 256,
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Handle modal submission."""
        # Collect field values
        field_values: dict[str, str] = {}
        validation_errors: list[str] = []

        for field_id, text_input in self._field_inputs.items():
            value = text_input.value.strip()
            field_values[field_id] = value

            # Find the field config for validation
            field_config = next(
                (f for f in self.config.submission_fields if f.id == field_id),
                None,
            )
            if field_config and field_config.validation_regex and value:
                if not re.match(field_config.validation_regex, value):
                    validation_errors.append(
                        f"**{field_config.label}** doesn't match the required format."
                    )

        if validation_errors:
            await interaction.response.send_message(
                "❌ **Validation Error**\n" + "\n".join(validation_errors),
                ephemeral=True,
            )
            return

        # Call the callback to handle submission
        await self.on_submit_callback(interaction, field_values)
