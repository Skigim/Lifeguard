import unittest


class ContentReviewConfigMigrationTests(unittest.TestCase):
    def test_from_firestore_reads_legacy_review_categories(self) -> None:
        from lifeguard.modules.content_review.config import ContentReviewConfig

        config = ContentReviewConfig.from_firestore(
            {
                "guild_id": 123,
                "review_categories": [
                    {
                        "id": "overall",
                        "name": "Overall",
                        "response_kind": "score",
                        "options": {
                            "min_value": 1,
                            "max_value": 5,
                            "allow_note": True,
                        },
                    }
                ],
            }
        )

        self.assertEqual(config.form_categories[0].id, "overall")
        self.assertEqual(config.form_categories[0].response_kind, "score")

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