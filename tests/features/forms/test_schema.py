import unittest


class FormSchemaTests(unittest.TestCase):
    def test_form_category_from_firestore_defaults_missing_response_kind_to_note(self) -> None:
        from lifeguard.features.forms.schema import FormCategory, NoteOptions

        restored = FormCategory.from_firestore(
            {
                "id": "note",
                "name": "Note",
            }
        )

        self.assertEqual(restored.response_kind, "note")
        self.assertIsInstance(restored.options, NoteOptions)

    def test_form_category_defaults_options_to_note_options(self) -> None:
        from lifeguard.features.forms.schema import FormCategory, NoteOptions

        category = FormCategory(id="note", name="Note")

        self.assertEqual(category.response_kind, "note")
        self.assertIsInstance(category.options, NoteOptions)
        self.assertEqual(
            category.to_firestore()["options"],
            NoteOptions().to_firestore(),
        )

    def test_form_category_direct_score_defaults_to_score_options(self) -> None:
        from lifeguard.features.forms.schema import FormCategory, ScoreOptions

        category = FormCategory(
            id="overall",
            name="Overall",
            response_kind="score",
        )

        self.assertEqual(
            category.to_firestore()["options"],
            ScoreOptions().to_firestore(),
        )

    def test_form_category_round_trips_score_options(self) -> None:
        from lifeguard.features.forms.schema import FormCategory, ScoreOptions

        category = FormCategory(
            id="overall",
            name="Overall",
            description="Rate overall quality",
            response_kind="score",
            required=True,
            options=ScoreOptions(min_value=1, max_value=5, allow_note=True),
        )

        restored = FormCategory.from_firestore(category.to_firestore())

        self.assertEqual(restored.response_kind, "score")
        self.assertEqual(restored.options.min_value, 1)
        self.assertEqual(restored.options.max_value, 5)
        self.assertTrue(restored.options.allow_note)

    def test_select_category_round_trips_choices(self) -> None:
        from lifeguard.features.forms.schema import (
            ChoiceOption,
            FormCategory,
            SelectOptions,
        )

        category = FormCategory(
            id="status",
            name="Status",
            response_kind="single_select",
            options=SelectOptions(
                choices=[
                    ChoiceOption(id="ready", label="Ready"),
                    ChoiceOption(id="blocked", label="Blocked"),
                ],
                min_selected=1,
                max_selected=1,
            ),
        )

        restored = FormCategory.from_firestore(category.to_firestore())

        self.assertEqual(restored.options.choices[0].id, "ready")
        self.assertEqual(restored.options.max_selected, 1)

    def test_text_boolean_and_note_categories_round_trip(self) -> None:
        from lifeguard.features.forms.schema import (
            BooleanOptions,
            FormCategory,
            NoteOptions,
            TextOptions,
        )

        text_category = FormCategory(
            id="summary",
            name="Summary",
            response_kind="text",
            options=TextOptions(
                style="paragraph",
                placeholder="Summarize the review",
                validation_regex="^.{10,}$",
            ),
        )
        boolean_category = FormCategory(
            id="approved",
            name="Approved",
            response_kind="boolean",
            options=BooleanOptions(true_label="Approve", false_label="Reject"),
        )
        note_category = FormCategory(
            id="note",
            name="Note",
            response_kind="note",
            options=NoteOptions(
                placeholder="Add supporting notes",
                required_reference=True,
            ),
        )

        restored_text = FormCategory.from_firestore(text_category.to_firestore())
        restored_boolean = FormCategory.from_firestore(boolean_category.to_firestore())
        restored_note = FormCategory.from_firestore(note_category.to_firestore())

        self.assertEqual(restored_text.options.style, "paragraph")
        self.assertEqual(restored_boolean.options.true_label, "Approve")
        self.assertTrue(restored_note.options.required_reference)

    def test_form_category_rejects_mismatched_options_during_construction(self) -> None:
        from lifeguard.features.forms.schema import (
            FormCategory,
            InvalidFormSchemaError,
            NoteOptions,
        )

        with self.assertRaises(InvalidFormSchemaError):
            FormCategory(
                id="overall",
                name="Overall",
                response_kind="score",
                options=NoteOptions(),
            )

    def test_text_options_from_firestore_rejects_unsupported_style(self) -> None:
        from lifeguard.features.forms.schema import InvalidFormSchemaError, TextOptions

        with self.assertRaises(InvalidFormSchemaError):
            TextOptions.from_firestore({"style": "markdown"})

    def test_multi_select_category_round_trips_selection_limits(self) -> None:
        from lifeguard.features.forms.schema import (
            ChoiceOption,
            FormCategory,
            SelectOptions,
        )

        category = FormCategory(
            id="tags",
            name="Tags",
            response_kind="multi_select",
            options=SelectOptions(
                choices=[
                    ChoiceOption(id="fun", label="Fun"),
                    ChoiceOption(id="clear", label="Clear"),
                ],
                min_selected=1,
                max_selected=2,
            ),
        )

        restored = FormCategory.from_firestore(category.to_firestore())

        self.assertEqual(restored.response_kind, "multi_select")
        self.assertEqual(restored.options.min_selected, 1)
        self.assertEqual(restored.options.max_selected, 2)

    def test_form_field_round_trips(self) -> None:
        from lifeguard.features.forms.schema import FormField

        field = FormField(
            id="game_link",
            label="Game Link",
            field_type="url",
            required=False,
            placeholder="https://example.com/replay/123",
            validation_regex=r"^https://",
        )

        restored = FormField.from_firestore(field.to_firestore())

        self.assertEqual(restored.field_type, "url")
        self.assertFalse(restored.required)
        self.assertEqual(restored.validation_regex, r"^https://")

    def test_form_field_rejects_unknown_field_type(self) -> None:
        from lifeguard.features.forms.schema import FormField, InvalidFormSchemaError

        with self.assertRaises(InvalidFormSchemaError):
            FormField.from_firestore(
                {
                    "id": "bad",
                    "label": "Bad",
                    "field_type": "markdown",
                }
            )

    def test_form_field_rejects_unknown_field_type_during_construction(self) -> None:
        from lifeguard.features.forms.schema import FormField, InvalidFormSchemaError

        with self.assertRaises(InvalidFormSchemaError):
            FormField(
                id="bad",
                label="Bad",
                field_type="markdown",
            )

    def test_unknown_response_kind_is_rejected(self) -> None:
        from lifeguard.features.forms.schema import InvalidFormSchemaError, FormCategory

        with self.assertRaises(InvalidFormSchemaError):
            FormCategory.from_firestore(
                {
                    "id": "bad",
                    "name": "Bad",
                    "response_kind": "unsupported",
                    "options": {},
                }
            )


if __name__ == "__main__":
    unittest.main()