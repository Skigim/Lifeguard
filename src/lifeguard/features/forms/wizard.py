from __future__ import annotations

import re
from collections.abc import Callable, Coroutine
from datetime import datetime, timezone
from typing import Any, cast

import discord

from lifeguard.features.forms.models import FormCategoryResponse, FormResponseSession
from lifeguard.features.forms.schema import (
    FormCategory,
    FormField,
    NoteOptions,
    ScoreOptions,
    SelectOptions,
    TextOptions,
)
from lifeguard.features.forms.submission_modal import FormSubmissionModal


def _is_empty_value(value: int | str | bool | list[str] | None) -> bool:
    return value is None or value == "" or value == []


def _response_label(response: FormCategoryResponse) -> str:
    value = response.value
    if response.response_kind == "boolean":
        return "Yes" if cast(bool, value) else "No"
    if response.response_kind == "multi_select":
        return ", ".join(cast(list[str], value))
    return str(value)


def validate_category_response(
    category: FormCategory,
    response: FormCategoryResponse,
) -> str | None:
    if response.category_id != category.id:
        return f"Response does not belong to {category.name}."

    if response.response_kind != category.response_kind:
        return f"{category.name} has an invalid response type."

    if category.required and _is_empty_value(response.value):
        return f"{category.name} is required."

    if _is_empty_value(response.value):
        return None

    if category.response_kind == "score":
        options = cast(ScoreOptions, category.options)
        score = cast(int, response.value)
        if score < options.min_value or score > options.max_value:
            return f"{category.name} must be between {options.min_value} and {options.max_value}."
        return None

    if category.response_kind in {"single_select", "multi_select"}:
        options = cast(SelectOptions, category.options)
        allowed_values = {choice.id for choice in options.choices}

        if category.response_kind == "single_select":
            value = cast(str, response.value)
            if value not in allowed_values:
                return f"{category.name} has an invalid selection."
            return None

        selected_values = cast(list[str], response.value)
        if len(selected_values) < options.min_selected:
            return f"{category.name} requires at least {options.min_selected} selection(s)."
        if len(selected_values) > options.max_selected:
            return f"{category.name} allows at most {options.max_selected} selection(s)."
        if any(value not in allowed_values for value in selected_values):
            return f"{category.name} has an invalid selection."
        return None

    if category.response_kind == "text":
        options = cast(TextOptions, category.options)
        value = cast(str, response.value).strip()
        if options.validation_regex and not re.match(options.validation_regex, value):
            return f"{category.name} doesn't match the required format."
        return None

    if category.response_kind == "note":
        options = cast(NoteOptions, category.options)
        if options.required_reference and not response.reference.strip():
            return f"{category.name} requires a reference."
        return None

    return None


def build_summary_lines(responses: list[FormCategoryResponse]) -> list[str]:
    lines: list[str] = []
    for response in responses:
        line = f"{response.category_id}: {_response_label(response)}"
        if response.note.strip():
            line = f"{line} ({response.note.strip()})"
        lines.append(line)
    return lines


class FormWizardView(discord.ui.View):
    def __init__(
        self,
        categories: list[FormCategory],
        session: FormResponseSession,
        on_publish_callback: Callable[
            [FormResponseSession],
            Coroutine[Any, Any, None],
        ],
        timeout: float = 900.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.categories = categories
        self.session = session
        self.on_publish_callback = on_publish_callback
        self.current_step = 0
        self._message: discord.Message | None = None
        self._sync_components()

    @property
    def current_category(self) -> FormCategory | None:
        if 0 <= self.current_step < len(self.categories):
            return self.categories[self.current_step]
        return None

    @property
    def is_summary_step(self) -> bool:
        return self.current_step >= len(self.categories)

    def build_embed(self) -> discord.Embed:
        if self.is_summary_step:
            return self._build_summary_embed()
        return self._build_category_embed()

    def _sync_components(self) -> None:
        self.clear_items()
        if self.is_summary_step:
            self._add_summary_components()
            return
        self._add_category_components()

    def _response_for(self, category_id: str) -> FormCategoryResponse | None:
        for response in self.session.responses:
            if response.category_id == category_id:
                return response
        return None

    def _upsert_response(self, response: FormCategoryResponse) -> None:
        for index, existing in enumerate(self.session.responses):
            if existing.category_id == response.category_id:
                self.session.responses[index] = response
                return
        self.session.responses.append(response)

    def _active_step_error(self) -> str | None:
        category = self.current_category
        if category is None:
            return None

        response = self._response_for(category.id)
        if response is None:
            if category.required:
                return f"{category.name} is required."
            return None

        return validate_category_response(category, response)

    def _build_category_embed(self) -> discord.Embed:
        category = self.current_category
        assert category is not None

        embed = discord.Embed(
            title=f"Step {self.current_step + 1}/{len(self.categories)}: {category.name}",
            description=category.description or "Provide a response for this category.",
            color=discord.Color.blue(),
        )

        response = self._response_for(category.id)
        if response is not None and not _is_empty_value(response.value):
            embed.add_field(
                name="Current Response",
                value=_response_label(response),
                inline=False,
            )
            if response.reference.strip():
                embed.add_field(
                    name="Reference",
                    value=response.reference.strip(),
                    inline=False,
                )

        error = self._active_step_error()
        if error:
            embed.add_field(name="Validation", value=error, inline=False)

        return embed

    def _build_summary_embed(self) -> discord.Embed:
        lines = build_summary_lines(self.session.responses)
        description = "\n".join(lines) if lines else "No responses recorded."
        return discord.Embed(
            title="Form Summary",
            description=description,
            color=discord.Color.green(),
        )

    def _add_category_components(self) -> None:
        category = self.current_category
        if category is None:
            return

        if category.response_kind in {"score", "boolean", "single_select", "multi_select"}:
            self.add_item(self._build_select(category))
        else:
            response_button = discord.ui.Button(
                label="Edit Response" if self._response_for(category.id) else "Add Response",
                style=discord.ButtonStyle.secondary,
                custom_id="wizard_open_modal",
            )
            response_button.callback = self._on_open_modal
            self.add_item(response_button)

        if self.current_step > 0:
            back_button = discord.ui.Button(
                label="Back",
                style=discord.ButtonStyle.secondary,
                custom_id="wizard_back",
            )
            back_button.callback = self._on_back
            self.add_item(back_button)

        next_button = discord.ui.Button(
            label="Review Summary" if self.current_step == len(self.categories) - 1 else "Next",
            style=discord.ButtonStyle.primary,
            custom_id="wizard_next",
            disabled=self._active_step_error() is not None,
        )
        next_button.callback = self._on_next
        self.add_item(next_button)

        cancel_button = discord.ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.danger,
            custom_id="wizard_cancel",
        )
        cancel_button.callback = self._on_cancel
        self.add_item(cancel_button)

    def _add_summary_components(self) -> None:
        edit_button = discord.ui.Button(
            label="Edit",
            style=discord.ButtonStyle.secondary,
            custom_id="wizard_edit",
        )
        edit_button.callback = self._on_edit
        self.add_item(edit_button)

        publish_button = discord.ui.Button(
            label="Publish",
            style=discord.ButtonStyle.success,
            custom_id="wizard_publish",
            disabled=bool(self.categories) and any(
                validate_category_response(category, response)
                for category in self.categories
                for response in [self._response_for(category.id)]
                if response is not None
            ) or any(
                category.required and self._response_for(category.id) is None
                for category in self.categories
            ),
        )
        publish_button.callback = self._on_publish
        self.add_item(publish_button)

        cancel_button = discord.ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.danger,
            custom_id="wizard_cancel",
        )
        cancel_button.callback = self._on_cancel
        self.add_item(cancel_button)

    def _build_select(self, category: FormCategory) -> discord.ui.Select:
        response = self._response_for(category.id)
        options: list[discord.SelectOption]
        placeholder = f"Select {category.name}"
        min_values = 1
        max_values = 1

        if category.response_kind == "score":
            score_options = cast(ScoreOptions, category.options)
            selected = response.value if response is not None else None
            options = [
                discord.SelectOption(
                    label=str(value),
                    value=str(value),
                    default=(selected == value),
                )
                for value in range(score_options.min_value, score_options.max_value + 1)
            ]
        elif category.response_kind == "boolean":
            selected = response.value if response is not None else None
            options = [
                discord.SelectOption(label="Yes", value="true", default=(selected is True)),
                discord.SelectOption(label="No", value="false", default=(selected is False)),
            ]
        else:
            select_options = cast(SelectOptions, category.options)
            selected_values = response.value if response is not None else []
            if not isinstance(selected_values, list):
                selected_values = [selected_values]
            options = [
                discord.SelectOption(
                    label=choice.label,
                    value=choice.id,
                    default=(choice.id in selected_values),
                )
                for choice in select_options.choices
            ]
            min_values = 1 if category.response_kind == "single_select" else select_options.min_selected
            max_values = 1 if category.response_kind == "single_select" else select_options.max_selected

        select = discord.ui.Select(
            placeholder=placeholder,
            options=options,
            min_values=min_values,
            max_values=max_values,
            custom_id="wizard_select",
        )
        select.callback = self._on_select_submit
        return select

    def _modal_fields_for_category(self, category: FormCategory) -> list[FormField]:
        response = self._response_for(category.id)
        if category.response_kind == "text":
            options = cast(TextOptions, category.options)
            field_type = "paragraph" if options.style == "paragraph" else "short_text"
            return [
                FormField(
                    id="value",
                    label=category.name,
                    field_type=field_type,
                    required=category.required,
                    placeholder=options.placeholder,
                    validation_regex=options.validation_regex,
                )
            ]

        note_options = cast(NoteOptions, category.options)
        reference_required = note_options.required_reference
        fields = [
            FormField(
                id="reference",
                label=f"{category.name} Reference",
                field_type="short_text",
                required=reference_required,
                placeholder="Add context or evidence",
            ),
            FormField(
                id="value",
                label=category.name,
                field_type="paragraph",
                required=category.required,
                placeholder=note_options.placeholder,
            ),
        ]
        if response is not None:
            return fields
        return fields

    async def _on_select_submit(self, interaction: discord.Interaction) -> None:
        category = self.current_category
        if category is None:
            return

        values = interaction.data.get("values", []) if interaction.data else []
        existing = self._response_for(category.id)
        note = existing.note if existing is not None else ""
        reference = existing.reference if existing is not None else ""

        if category.response_kind == "score":
            value: int | str | bool | list[str] = int(values[0])
        elif category.response_kind == "boolean":
            value = values[0] == "true"
        elif category.response_kind == "single_select":
            value = values[0]
        else:
            value = list(values)

        self._upsert_response(
            FormCategoryResponse(
                category_id=category.id,
                response_kind=category.response_kind,
                value=value,
                note=note,
                reference=reference,
            )
        )
        self._sync_components()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _on_open_modal(self, interaction: discord.Interaction) -> None:
        category = self.current_category
        if category is None:
            return

        async def _handle_modal_submit(
            modal_interaction: discord.Interaction,
            field_values: dict[str, str],
        ) -> None:
            self._upsert_response(
                FormCategoryResponse(
                    category_id=category.id,
                    response_kind=category.response_kind,
                    value=field_values.get("value", ""),
                    reference=field_values.get("reference", ""),
                )
            )
            self._sync_components()
            await modal_interaction.response.edit_message(
                embed=self.build_embed(),
                view=self,
            )

        modal = FormSubmissionModal(
            title=category.name,
            fields=self._modal_fields_for_category(category),
            on_submit_callback=_handle_modal_submit,
        )
        await interaction.response.send_modal(modal)

    async def _on_back(self, interaction: discord.Interaction) -> None:
        self.current_step = max(0, self.current_step - 1)
        self._sync_components()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _on_next(self, interaction: discord.Interaction) -> None:
        self.current_step += 1
        self._sync_components()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _on_edit(self, interaction: discord.Interaction) -> None:
        self.current_step = 0
        self._sync_components()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _on_publish(self, interaction: discord.Interaction) -> None:
        self.session.status = "completed"
        self.session.completed_at = datetime.now(timezone.utc)
        await interaction.response.defer()
        self.stop()
        await self.on_publish_callback(self.session)

    async def _on_cancel(self, interaction: discord.Interaction) -> None:
        self.stop()
        await interaction.response.edit_message(
            content="❌ Form cancelled.",
            embed=None,
            view=None,
        )

    async def on_timeout(self) -> None:
        self.stop()