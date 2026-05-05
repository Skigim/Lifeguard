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

    def test_build_summary_lines_formats_scalar_and_multi_select_values(self) -> None:
        from lifeguard.features.forms.models import FormCategoryResponse
        from lifeguard.features.forms.wizard import build_summary_lines

        lines = build_summary_lines(
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
                    category_id="tags",
                    response_kind="multi_select",
                    value=["clear", "concise"],
                ),
            ]
        )

        self.assertEqual(
            lines,
            [
                "overall: 5 (Ready)",
                "approved: Yes",
                "tags: clear, concise",
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


if __name__ == "__main__":
    unittest.main()