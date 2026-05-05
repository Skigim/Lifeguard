from __future__ import annotations

import re
from collections.abc import Callable, Coroutine
from typing import Any

import discord

from lifeguard.features.forms.schema import FormField, InvalidFormSchemaError

_DISCORD_MODAL_MAX_FIELDS = 5


def _to_text_style(field_type: str) -> discord.TextStyle:
    if field_type == "paragraph":
        return discord.TextStyle.paragraph
    return discord.TextStyle.short


def _max_length_for(field_type: str) -> int:
    if field_type == "paragraph":
        return 1024
    return 256


def _input_value(text_input: discord.ui.TextInput) -> str:
    value = getattr(text_input, "_value", None)
    if value is None:
        value = text_input.value
    if value is None:
        value = text_input.default
    if value is None:
        return ""
    return str(value)


class FormSubmissionModal(discord.ui.Modal):
    def __init__(
        self,
        title: str,
        fields: list[FormField],
        on_submit_callback: Callable[
            [discord.Interaction, dict[str, str]],
            Coroutine[Any, Any, None],
        ],
        initial_values: dict[str, str] | None = None,
    ) -> None:
        super().__init__(title=title)
        if len(fields) > _DISCORD_MODAL_MAX_FIELDS:
            raise InvalidFormSchemaError(
                "Form submission modals support at most "
                f"{_DISCORD_MODAL_MAX_FIELDS} fields; received {len(fields)}."
            )

        self.fields = fields
        self.on_submit_callback = on_submit_callback
        self._field_inputs: dict[str, discord.ui.TextInput] = {}

        for field in self.fields:
            text_input = discord.ui.TextInput(
                label=field.label,
                style=_to_text_style(field.field_type),
                placeholder=field.placeholder or None,
                required=field.required,
                max_length=_max_length_for(field.field_type),
                default=(initial_values or {}).get(field.id) or None,
            )
            self._field_inputs[field.id] = text_input
            self.add_item(text_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        field_values: dict[str, str] = {}
        validation_errors: list[str] = []

        for field in self.fields:
            text_input = self._field_inputs[field.id]
            value = _input_value(text_input).strip()
            field_values[field.id] = value

            if field.validation_regex and value:
                if not re.match(field.validation_regex, value):
                    validation_errors.append(
                        f"**{field.label}** doesn't match the required format."
                    )

        if validation_errors:
            await interaction.response.send_message(
                "❌ **Validation Error**\n" + "\n".join(validation_errors),
                ephemeral=True,
            )
            return

        await self.on_submit_callback(interaction, field_values)