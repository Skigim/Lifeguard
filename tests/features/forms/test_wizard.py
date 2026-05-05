from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock

import discord


class FormWizardHelperTests(unittest.TestCase):
    def test_validate_required_text_response(self) -> None:
        from lifeguard.features.forms.models import FormCategoryResponse
        from lifeguard.features.forms.schema import FormCategory, TextOptions
        from lifeguard.features.forms.wizard import validate_category_response

        category = FormCategory(
            id="context",
            name="Context",
            response_kind="text",
            required=True,
            options=TextOptions(style="paragraph"),
        )

        error = validate_category_response(
            category,
            FormCategoryResponse(category_id="context", response_kind="text", value=""),
        )

        self.assertEqual(error, "Context is required.")

    def test_validate_text_response_rejects_regex_mismatch(self) -> None:
        from lifeguard.features.forms.models import FormCategoryResponse
        from lifeguard.features.forms.schema import FormCategory, TextOptions
        from lifeguard.features.forms.wizard import validate_category_response

        category = FormCategory(
            id="clip",
            name="Clip",
            response_kind="text",
            required=True,
            options=TextOptions(style="short", validation_regex=r"^https://"),
        )

        error = validate_category_response(
            category,
            FormCategoryResponse(
                category_id="clip",
                response_kind="text",
                value="http://invalid.example",
            ),
        )

        self.assertEqual(error, "Clip doesn't match the required format.")

    def test_build_summary_lines_use_category_names_and_user_facing_labels(self) -> None:
        from lifeguard.features.forms.models import FormCategoryResponse
        from lifeguard.features.forms.schema import (
            BooleanOptions,
            ChoiceOption,
            FormCategory,
            SelectOptions,
            ScoreOptions,
        )
        from lifeguard.features.forms.wizard import build_summary_lines

        lines = build_summary_lines(
            [
                FormCategory(
                    id="overall",
                    name="Overall Score",
                    response_kind="score",
                    options=ScoreOptions(min_value=1, max_value=5, allow_note=True),
                ),
                FormCategory(
                    id="approved",
                    name="Approval",
                    response_kind="boolean",
                    options=BooleanOptions(true_label="Pass", false_label="Needs Work"),
                ),
                FormCategory(
                    id="status",
                    name="Status",
                    response_kind="single_select",
                    options=SelectOptions(
                        choices=[
                            ChoiceOption(id="ready", label="Ready to Publish"),
                            ChoiceOption(id="blocked", label="Blocked"),
                        ]
                    ),
                ),
                FormCategory(
                    id="tags",
                    name="Highlights",
                    response_kind="multi_select",
                    options=SelectOptions(
                        choices=[
                            ChoiceOption(id="clear", label="Clear"),
                            ChoiceOption(id="concise", label="Concise"),
                        ],
                        min_selected=1,
                        max_selected=2,
                    ),
                ),
            ],
            [
                FormCategoryResponse(
                    category_id="overall",
                    response_kind="score",
                    value=5,
                    note="Ready",
                ),
                FormCategoryResponse(
                    category_id="approved",
                    response_kind="boolean",
                    value=True,
                ),
                FormCategoryResponse(
                    category_id="status",
                    response_kind="single_select",
                    value="ready",
                ),
                FormCategoryResponse(
                    category_id="tags",
                    response_kind="multi_select",
                    value=["clear", "concise"],
                ),
            ]
        )

        self.assertEqual(
            lines,
            [
                "Overall Score: 5 (Ready)",
                "Approval: Pass",
                "Status: Ready to Publish",
                "Highlights: Clear, Concise",
            ],
        )


class FormSubmissionModalTests(unittest.IsolatedAsyncioTestCase):
    async def test_modal_builds_inputs_and_blocks_invalid_regex_submission(self) -> None:
        from lifeguard.features.forms.schema import FormField
        from lifeguard.features.forms.submission_modal import FormSubmissionModal

        callback = AsyncMock()
        modal = FormSubmissionModal(
            title="Submit",
            fields=[
                FormField(
                    id="clip_url",
                    label="Clip URL",
                    field_type="url",
                    validation_regex=r"^https://",
                ),
                FormField(
                    id="summary",
                    label="Summary",
                    field_type="paragraph",
                ),
            ],
            on_submit_callback=callback,
        )

        self.assertEqual(modal._field_inputs["clip_url"].style, discord.TextStyle.short)
        self.assertEqual(modal._field_inputs["summary"].style, discord.TextStyle.paragraph)

        modal._field_inputs["clip_url"]._value = "http://invalid.example"
        modal._field_inputs["summary"]._value = "  A summary  "
        interaction = MagicMock()
        interaction.response.send_message = AsyncMock()

        await modal.on_submit(interaction)

        callback.assert_not_awaited()
        interaction.response.send_message.assert_awaited_once()
        self.assertIn("Clip URL", interaction.response.send_message.await_args.args[0])

    async def test_modal_submits_trimmed_values_after_validation_passes(self) -> None:
        from lifeguard.features.forms.schema import FormField
        from lifeguard.features.forms.submission_modal import FormSubmissionModal

        callback = AsyncMock()
        modal = FormSubmissionModal(
            title="Submit",
            fields=[
                FormField(
                    id="clip_url",
                    label="Clip URL",
                    field_type="url",
                    validation_regex=r"^https://",
                ),
            ],
            on_submit_callback=callback,
        )
        modal._field_inputs["clip_url"]._value = "  https://valid.example  "
        interaction = MagicMock()
        interaction.response.send_message = AsyncMock()

        await modal.on_submit(interaction)

        callback.assert_awaited_once_with(
            interaction,
            {"clip_url": "https://valid.example"},
        )
        interaction.response.send_message.assert_not_awaited()


class FormWizardViewTests(unittest.IsolatedAsyncioTestCase):
    async def test_boolean_select_uses_schema_labels(self) -> None:
        from lifeguard.features.forms.models import FormResponseSession
        from lifeguard.features.forms.schema import BooleanOptions, FormCategory
        from lifeguard.features.forms.wizard import FormWizardView

        view = FormWizardView(
            categories=[
                FormCategory(
                    id="approved",
                    name="Approval",
                    response_kind="boolean",
                    required=True,
                    options=BooleanOptions(true_label="Pass", false_label="Needs Work"),
                )
            ],
            session=FormResponseSession(
                id="session-1",
                guild_id=1,
                feature_key="shared_forms",
                owner_id="submission-1",
                responder_id=2,
            ),
            on_publish_callback=AsyncMock(),
        )

        select = next(item for item in view.children if isinstance(item, discord.ui.Select))

        self.assertEqual([option.label for option in select.options], ["Pass", "Needs Work"])

    async def test_note_modal_reopens_with_existing_values_and_preserves_untouched_fields(
        self,
    ) -> None:
        from lifeguard.features.forms.models import FormCategoryResponse, FormResponseSession
        from lifeguard.features.forms.schema import FormCategory, NoteOptions
        from lifeguard.features.forms.wizard import FormWizardView

        view = FormWizardView(
            categories=[
                FormCategory(
                    id="details",
                    name="Details",
                    response_kind="note",
                    required=True,
                    options=NoteOptions(placeholder="Add context", required_reference=True),
                )
            ],
            session=FormResponseSession(
                id="session-1",
                guild_id=1,
                feature_key="shared_forms",
                owner_id="submission-1",
                responder_id=2,
                responses=[
                    FormCategoryResponse(
                        category_id="details",
                        response_kind="note",
                        value="Initial summary",
                        reference="Clip 00:12",
                    )
                ],
            ),
            on_publish_callback=AsyncMock(),
        )

        interaction = MagicMock()
        interaction.response.send_modal = AsyncMock()

        await view._on_open_modal(interaction)

        modal = interaction.response.send_modal.await_args.args[0]
        self.assertEqual(modal._field_inputs["reference"].default, "Clip 00:12")
        self.assertEqual(modal._field_inputs["value"].default, "Initial summary")

        modal._field_inputs["value"]._value = "Updated summary"
        modal_interaction = MagicMock()
        modal_interaction.response.edit_message = AsyncMock()

        await modal.on_submit(modal_interaction)

        response = view._response_for("details")
        self.assertIsNotNone(response)
        self.assertEqual(response.value, "Updated summary")
        self.assertEqual(response.reference, "Clip 00:12")

    async def test_score_category_with_allow_note_supports_note_and_reference_details(self) -> None:
        from lifeguard.features.forms.models import FormResponseSession
        from lifeguard.features.forms.schema import FormCategory, ScoreOptions
        from lifeguard.features.forms.wizard import FormWizardView

        view = FormWizardView(
            categories=[
                FormCategory(
                    id="overall",
                    name="Overall",
                    response_kind="score",
                    required=True,
                    options=ScoreOptions(min_value=1, max_value=5, allow_note=True),
                )
            ],
            session=FormResponseSession(
                id="session-1",
                guild_id=1,
                feature_key="shared_forms",
                owner_id="submission-1",
                responder_id=2,
            ),
            on_publish_callback=AsyncMock(),
        )

        select_interaction = MagicMock()
        select_interaction.data = {"values": ["4"]}
        select_interaction.response.edit_message = AsyncMock()

        await view._on_select_submit(select_interaction)

        details_button = next(
            item
            for item in view.children
            if isinstance(item, discord.ui.Button) and item.custom_id == "wizard_open_modal"
        )
        self.assertEqual(details_button.label, "Add Details")

        open_modal_interaction = MagicMock()
        open_modal_interaction.response.send_modal = AsyncMock()

        await view._on_open_modal(open_modal_interaction)

        modal = open_modal_interaction.response.send_modal.await_args.args[0]
        self.assertEqual(set(modal._field_inputs), {"reference", "note"})

        modal._field_inputs["reference"]._value = "Clip 00:12"
        modal._field_inputs["note"]._value = "Needs a stronger hook"
        modal_interaction = MagicMock()
        modal_interaction.response.edit_message = AsyncMock()

        await modal.on_submit(modal_interaction)

        response = view._response_for("overall")
        self.assertIsNotNone(response)
        self.assertEqual(response.value, 4)
        self.assertEqual(response.reference, "Clip 00:12")
        self.assertEqual(response.note, "Needs a stronger hook")

    async def test_wizard_view_tracks_current_step_and_disables_progress_for_missing_required_response(
        self,
    ) -> None:
        from lifeguard.features.forms.models import FormResponseSession
        from lifeguard.features.forms.schema import FormCategory, ScoreOptions
        from lifeguard.features.forms.wizard import FormWizardView

        view = FormWizardView(
            categories=[
                FormCategory(
                    id="overall",
                    name="Overall",
                    response_kind="score",
                    required=True,
                    options=ScoreOptions(min_value=1, max_value=5),
                )
            ],
            session=FormResponseSession(
                id="session-1",
                guild_id=1,
                feature_key="content_review",
                owner_id="submission-1",
                responder_id=2,
            ),
            on_publish_callback=AsyncMock(),
        )

        self.assertEqual(view.current_step, 0)
        select = next(item for item in view.children if isinstance(item, discord.ui.Select))
        next_button = next(
            item
            for item in view.children
            if isinstance(item, discord.ui.Button) and item.custom_id == "wizard_next"
        )

        self.assertEqual(select.placeholder, "Select Overall")
        self.assertTrue(next_button.disabled)

    async def test_wizard_uses_generic_default_copy_for_summary_and_timeout(self) -> None:
        from lifeguard.features.forms.models import FormResponseSession
        from lifeguard.features.forms.schema import FormCategory, ScoreOptions
        from lifeguard.features.forms.wizard import FormWizardView

        view = FormWizardView(
            categories=[
                FormCategory(
                    id="overall",
                    name="Overall",
                    response_kind="score",
                    required=True,
                    options=ScoreOptions(min_value=1, max_value=5),
                )
            ],
            session=FormResponseSession(
                id="session-1",
                guild_id=1,
                feature_key="shared_forms",
                owner_id="submission-1",
                responder_id=2,
            ),
            on_publish_callback=AsyncMock(),
        )

        next_button = next(
            item
            for item in view.children
            if isinstance(item, discord.ui.Button) and item.custom_id == "wizard_next"
        )
        self.assertEqual(next_button.label, "View Summary")

        view.current_step = len(view.categories)
        view._sync_components()
        self.assertEqual(view.build_embed().title, "Form Summary")

        view._message = MagicMock()
        view._message.edit = AsyncMock()
        await view.on_timeout()

        view._message.edit.assert_awaited_once_with(
            content="⏰ Form timed out.",
            embed=None,
            view=None,
        )


if __name__ == "__main__":
    unittest.main()