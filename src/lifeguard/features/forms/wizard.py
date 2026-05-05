from __future__ import annotations

import re
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any, cast

import discord

from lifeguard.features.forms.models import FormCategoryResponse, FormResponseSession
from lifeguard.features.forms.schema import (
    BooleanOptions,
    FormCategory,
    FormField,
    FormFieldType,
    NoteOptions,
    ScoreOptions,
    SelectOptions,
    TextOptions,
)
from lifeguard.features.forms.submission_modal import FormSubmissionModal


@dataclass(frozen=True)
class FormWizardCopy:
    category_description_fallback: str = "Provide a response for this category."
    current_response_field_name: str = "Current Response"
    note_field_name: str = "Note"
    reference_field_name: str = "Reference"
    summary_title: str = "Form Summary"
    summary_empty_description: str = "No responses recorded."
    next_button_label: str = "Next"
    final_step_next_label: str = "View Summary"
    edit_button_label: str = "Edit"
    publish_button_label: str = "Publish"
    cancel_button_label: str = "Cancel"
    cancel_message: str = "❌ Form cancelled."
    timeout_message: str = "⏰ Form timed out."


def _is_empty_value(value: int | str | bool | list[str] | None) -> bool:
    return value is None or value == "" or value == []


def _select_choice_label(options: SelectOptions, value: str) -> str:
    for choice in options.choices:
        if choice.id == value:
            return choice.label
    return value


def _score_options(category: FormCategory) -> ScoreOptions:
    return cast(ScoreOptions, category.options)


def _select_options(category: FormCategory) -> SelectOptions:
    return cast(SelectOptions, category.options)


def _text_options(category: FormCategory) -> TextOptions:
    return cast(TextOptions, category.options)


def _note_options(category: FormCategory) -> NoteOptions:
    return cast(NoteOptions, category.options)


def _boolean_options(category: FormCategory) -> BooleanOptions:
    return cast(BooleanOptions, category.options)


def _bind_component_callback(
    component: object,
    callback: Callable[[discord.Interaction], Coroutine[Any, Any, None]],
) -> None:
    setattr(component, "callback", callback)


def _response_label(
    category: FormCategory | None, response: FormCategoryResponse
) -> str:
    value = response.value
    if response.response_kind == "boolean":
        if category is not None:
            boolean_options = _boolean_options(category)
            return (
                boolean_options.true_label
                if cast(bool, value)
                else boolean_options.false_label
            )
        return "Yes" if cast(bool, value) else "No"
    if response.response_kind == "single_select":
        if category is not None:
            select_options = _select_options(category)
            return _select_choice_label(select_options, cast(str, value))
        return str(value)
    if response.response_kind == "multi_select":
        if category is not None:
            select_options = _select_options(category)
            return ", ".join(
                _select_choice_label(select_options, selected)
                for selected in cast(list[str], value)
            )
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
        score_options = _score_options(category)
        score = cast(int, response.value)
        if score < score_options.min_value or score > score_options.max_value:
            return (
                f"{category.name} must be between {score_options.min_value} "
                f"and {score_options.max_value}."
            )
        return None

    if category.response_kind in {"single_select", "multi_select"}:
        select_options = _select_options(category)
        allowed_values = {choice.id for choice in select_options.choices}

        if category.response_kind == "single_select":
            value = cast(str, response.value)
            if value not in allowed_values:
                return f"{category.name} has an invalid selection."
            return None

        selected_values = cast(list[str], response.value)
        if len(selected_values) < select_options.min_selected:
            return (
                f"{category.name} requires at least "
                f"{select_options.min_selected} selection(s)."
            )
        if len(selected_values) > select_options.max_selected:
            return (
                f"{category.name} allows at most "
                f"{select_options.max_selected} selection(s)."
            )
        if any(value not in allowed_values for value in selected_values):
            return f"{category.name} has an invalid selection."
        return None

    if category.response_kind == "text":
        text_options = _text_options(category)
        value = cast(str, response.value).strip()
        if text_options.validation_regex and not re.match(
            text_options.validation_regex, value
        ):
            return f"{category.name} doesn't match the required format."
        return None

    if category.response_kind == "note":
        note_options = _note_options(category)
        if note_options.required_reference and not response.reference.strip():
            return f"{category.name} requires a reference."
        return None

    return None


def build_summary_lines(
    categories: list[FormCategory],
    responses: list[FormCategoryResponse],
) -> list[str]:
    categories_by_id = {category.id: category for category in categories}
    lines: list[str] = []
    for response in responses:
        category = categories_by_id.get(response.category_id)
        category_name = category.name if category is not None else response.category_id
        line = f"{category_name}: {_response_label(category, response)}"
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
        copy: FormWizardCopy | None = None,
        select_placeholder_builder: Callable[[FormCategory], str] | None = None,
        detail_button_label_builder: Callable[
            [FormCategory, FormCategoryResponse | None],
            str,
        ]
        | None = None,
        detail_modal_visibility_builder: Callable[
            [FormCategory, FormCategoryResponse | None],
            bool,
        ]
        | None = None,
        summary_embed_builder: Callable[
            [list[FormCategory], FormResponseSession],
            discord.Embed,
        ]
        | None = None,
        timeout: float = 900.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.categories = categories
        self.session = session
        self.on_publish_callback = on_publish_callback
        self.copy = copy or FormWizardCopy()
        self.select_placeholder_builder = select_placeholder_builder
        self.detail_button_label_builder = detail_button_label_builder
        self.detail_modal_visibility_builder = detail_modal_visibility_builder
        self.summary_embed_builder = summary_embed_builder
        self.current_step = 0
        self._message: discord.Message | None = None
        self._sync_components()

    def attach_message(self, message: discord.Message) -> FormWizardView:
        self._message = message
        return self

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
            description=category.description or self.copy.category_description_fallback,
            color=discord.Color.blue(),
        )

        response = self._response_for(category.id)
        if response is not None and not _is_empty_value(response.value):
            embed.add_field(
                name=self.copy.current_response_field_name,
                value=_response_label(category, response),
                inline=False,
            )
            if response.note.strip():
                embed.add_field(
                    name=self.copy.note_field_name,
                    value=response.note.strip(),
                    inline=False,
                )
            if response.reference.strip():
                embed.add_field(
                    name=self.copy.reference_field_name,
                    value=response.reference.strip(),
                    inline=False,
                )

        error = self._active_step_error()
        if error:
            embed.add_field(name="Validation", value=error, inline=False)

        return embed

    def _build_summary_embed(self) -> discord.Embed:
        if self.summary_embed_builder is not None:
            return self.summary_embed_builder(self.categories, self.session)

        lines = build_summary_lines(self.categories, self.session.responses)
        description = "\n".join(lines) if lines else self.copy.summary_empty_description
        return discord.Embed(
            title=self.copy.summary_title,
            description=description,
            color=discord.Color.green(),
        )

    def _supports_detail_modal(self, category: FormCategory) -> bool:
        response = self._response_for(category.id)
        if self.detail_modal_visibility_builder is not None:
            return self.detail_modal_visibility_builder(category, response)

        if category.response_kind in {"text", "note"}:
            return True
        if category.response_kind == "score":
            options = cast(ScoreOptions, category.options)
            return options.allow_note and response is not None
        return False

    def _modal_button_label(self, category: FormCategory) -> str:
        response = self._response_for(category.id)
        if self.detail_button_label_builder is not None:
            return self.detail_button_label_builder(category, response)

        if category.response_kind == "score":
            if response is not None and (
                response.note.strip() or response.reference.strip()
            ):
                return "Edit Details"
            return "Add Details"
        return "Edit Response" if response is not None else "Add Response"

    def _add_category_components(self) -> None:
        category = self.current_category
        if category is None:
            return

        if category.response_kind in {
            "score",
            "boolean",
            "single_select",
            "multi_select",
        }:
            self.add_item(self._build_select(category))
        if self._supports_detail_modal(category):
            response_button: discord.ui.Button[Any] = discord.ui.Button(
                label=self._modal_button_label(category),
                style=discord.ButtonStyle.secondary,
                custom_id="wizard_open_modal",
            )
            _bind_component_callback(response_button, self._on_open_modal)
            self.add_item(response_button)

        if self.current_step > 0:
            back_button: discord.ui.Button[Any] = discord.ui.Button(
                label="Back",
                style=discord.ButtonStyle.secondary,
                custom_id="wizard_back",
            )
            _bind_component_callback(back_button, self._on_back)
            self.add_item(back_button)

        next_button: discord.ui.Button[Any] = discord.ui.Button(
            label=(
                self.copy.final_step_next_label
                if self.current_step == len(self.categories) - 1
                else self.copy.next_button_label
            ),
            style=discord.ButtonStyle.primary,
            custom_id="wizard_next",
            disabled=self._active_step_error() is not None,
        )
        _bind_component_callback(next_button, self._on_next)
        self.add_item(next_button)

        cancel_button: discord.ui.Button[Any] = discord.ui.Button(
            label=self.copy.cancel_button_label,
            style=discord.ButtonStyle.danger,
            custom_id="wizard_cancel",
        )
        _bind_component_callback(cancel_button, self._on_cancel)
        self.add_item(cancel_button)

    def _add_summary_components(self) -> None:
        edit_button: discord.ui.Button[Any] = discord.ui.Button(
            label=self.copy.edit_button_label,
            style=discord.ButtonStyle.secondary,
            custom_id="wizard_edit",
        )
        _bind_component_callback(edit_button, self._on_edit)
        self.add_item(edit_button)

        publish_button: discord.ui.Button[Any] = discord.ui.Button(
            label=self.copy.publish_button_label,
            style=discord.ButtonStyle.success,
            custom_id="wizard_publish",
            disabled=bool(self.categories)
            and any(
                validate_category_response(category, response)
                for category in self.categories
                for response in [self._response_for(category.id)]
                if response is not None
            )
            or any(
                category.required and self._response_for(category.id) is None
                for category in self.categories
            ),
        )
        _bind_component_callback(publish_button, self._on_publish)
        self.add_item(publish_button)

        cancel_button: discord.ui.Button[Any] = discord.ui.Button(
            label=self.copy.cancel_button_label,
            style=discord.ButtonStyle.danger,
            custom_id="wizard_cancel",
        )
        _bind_component_callback(cancel_button, self._on_cancel)
        self.add_item(cancel_button)

    def _build_select(self, category: FormCategory) -> discord.ui.Select[Any]:
        response = self._response_for(category.id)
        options: list[discord.SelectOption]
        placeholder = (
            self.select_placeholder_builder(category)
            if self.select_placeholder_builder is not None
            else f"Select {category.name}"
        )
        min_values = 1
        max_values = 1

        if category.response_kind == "score":
            score_options = _score_options(category)
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
            boolean_options = _boolean_options(category)
            selected = response.value if response is not None else None
            options = [
                discord.SelectOption(
                    label=boolean_options.true_label,
                    value="true",
                    default=(selected is True),
                ),
                discord.SelectOption(
                    label=boolean_options.false_label,
                    value="false",
                    default=(selected is False),
                ),
            ]
        else:
            select_options = _select_options(category)
            selected_values = response.value if response is not None else []
            if not isinstance(selected_values, list):
                selected_values = [cast(str, selected_values)]
            options = [
                discord.SelectOption(
                    label=choice.label,
                    value=choice.id,
                    default=(choice.id in selected_values),
                )
                for choice in select_options.choices
            ]
            min_values = (
                1
                if category.response_kind == "single_select"
                else select_options.min_selected
            )
            max_values = (
                1
                if category.response_kind == "single_select"
                else select_options.max_selected
            )

        select: discord.ui.Select[Any] = discord.ui.Select(
            placeholder=placeholder,
            options=options,
            min_values=min_values,
            max_values=max_values,
            custom_id="wizard_select",
        )
        _bind_component_callback(select, self._on_select_submit)
        return select

    def _modal_fields_for_category(self, category: FormCategory) -> list[FormField]:
        if category.response_kind == "text":
            options = _text_options(category)
            field_type: FormFieldType = (
                "paragraph" if options.style == "paragraph" else "short_text"
            )
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

        if category.response_kind == "score":
            return [
                FormField(
                    id="reference",
                    label=f"{category.name} Reference",
                    field_type="short_text",
                    required=False,
                    placeholder="Add context or evidence",
                ),
                FormField(
                    id="note",
                    label=f"{category.name} Note",
                    field_type="paragraph",
                    required=False,
                    placeholder="Add supporting detail",
                ),
            ]

        note_options = _note_options(category)
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
        return fields

    def _modal_initial_values_for_category(
        self,
        category: FormCategory,
    ) -> dict[str, str]:
        existing = self._response_for(category.id)
        if existing is None:
            return {}

        if category.response_kind == "score":
            return {
                "reference": existing.reference,
                "note": existing.note,
            }

        if category.response_kind == "text":
            return {"value": cast(str, existing.value)}

        return {
            "reference": existing.reference,
            "value": cast(str, existing.value),
        }

    async def _on_select_submit(self, interaction: discord.Interaction) -> None:
        category = self.current_category
        if category is None:
            return

        data = cast(dict[str, object] | None, interaction.data)
        raw_values = data.get("values") if data is not None else []
        values = raw_values if isinstance(raw_values, list) else []
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
            existing = self._response_for(category.id)
            if category.response_kind == "score":
                if existing is None:
                    return
                score_value = existing.value
                if isinstance(score_value, bool) or not isinstance(score_value, int):
                    raise ValueError(
                        f"Score category {category.id!r} is missing an integer score"
                    )
                response = FormCategoryResponse(
                    category_id=category.id,
                    response_kind=category.response_kind,
                    value=score_value,
                    note=field_values.get("note", ""),
                    reference=field_values.get("reference", ""),
                )
            else:
                response = FormCategoryResponse(
                    category_id=category.id,
                    response_kind=category.response_kind,
                    value=field_values.get("value", ""),
                    note=existing.note if existing is not None else "",
                    reference=field_values.get("reference", ""),
                )
            self._upsert_response(response)
            self._sync_components()
            await modal_interaction.response.edit_message(
                embed=self.build_embed(),
                view=self,
            )

        modal = FormSubmissionModal(
            title=category.name,
            fields=self._modal_fields_for_category(category),
            initial_values=self._modal_initial_values_for_category(category),
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
        await interaction.response.defer()
        self.stop()
        await self.on_publish_callback(self.session)

    async def _on_cancel(self, interaction: discord.Interaction) -> None:
        self.stop()
        await interaction.response.edit_message(
            content=self.copy.cancel_message,
            embed=None,
            view=None,
        )

    async def on_timeout(self) -> None:
        self.stop()
        if self._message is not None:
            try:
                await self._message.edit(
                    content=self.copy.timeout_message,
                    embed=None,
                    view=None,
                )
            except discord.NotFound:
                pass
