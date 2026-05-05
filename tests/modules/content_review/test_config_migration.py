import unittest


class ContentReviewConfigMigrationTests(unittest.TestCase):
    def test_from_firestore_reads_true_legacy_review_categories_shape(self) -> None:
        from lifeguard.features.forms.schema import FormCategory, ScoreOptions
        from lifeguard.modules.content_review.config import ContentReviewConfig

        config = ContentReviewConfig.from_firestore(
            {
                "guild_id": 123,
                "review_categories": [
                    {
                        "id": "overall",
                        "name": "Overall",
                        "description": "Legacy score category",
                        "min_score": 2,
                        "max_score": 7,
                        "allow_notes": False,
                        "required": False,
                    }
                ],
            }
        )

        form_category = config.form_categories[0]
        review_category = config.review_categories[0]

        self.assertIsInstance(form_category, FormCategory)
        self.assertEqual(form_category.id, "overall")
        self.assertEqual(form_category.response_kind, "score")
        self.assertEqual(
            form_category.options,
            ScoreOptions(min_value=2, max_value=7, allow_note=False),
        )
        self.assertFalse(hasattr(FormCategory, "min_score"))
        self.assertIsNot(review_category, form_category)
        self.assertEqual(review_category.min_score, 2)
        self.assertEqual(review_category.max_score, 7)
        self.assertFalse(review_category.allow_notes)

    def test_to_firestore_writes_form_categories_only(self) -> None:
        from lifeguard.features.forms.schema import FormCategory, ScoreOptions
        from lifeguard.modules.content_review.config import ContentReviewConfig

        config = ContentReviewConfig(
            guild_id=123,
            form_categories=[
                FormCategory(
                    id="overall",
                    name="Overall",
                    response_kind="score",
                    options=ScoreOptions(min_value=1, max_value=5, allow_note=True),
                )
            ],
        )

        payload = config.to_firestore()

        self.assertIn("form_categories", payload)
        self.assertNotIn("review_categories", payload)


if __name__ == "__main__":
    unittest.main()