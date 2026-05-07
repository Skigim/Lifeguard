import unittest


class ContentReviewConfigMigrationTests(unittest.TestCase):
    def test_package_root_exports_forms_surface_without_legacy_aliases(self) -> None:
        import lifeguard.modules.content_review as content_review

        self.assertIn("ContentReviewConfig", content_review.__all__)
        self.assertIn("FormCategory", content_review.__all__)
        self.assertIn("FormField", content_review.__all__)
        self.assertNotIn("ReviewCategory", content_review.__all__)
        self.assertNotIn("SubmissionField", content_review.__all__)

    def test_default_config_uses_forms_native_runtime_lists(self) -> None:
        from lifeguard.features.forms.schema import FormCategory, FormField, ScoreOptions
        from lifeguard.modules.content_review.config import ContentReviewConfig

        config = ContentReviewConfig.default(123)

        self.assertIsInstance(config.submission_fields[0], FormField)
        self.assertIsInstance(config.form_categories[0], FormCategory)
        self.assertEqual(config.form_categories[0].response_kind, "score")
        self.assertEqual(
            config.form_categories[0].options,
            ScoreOptions(min_value=1, max_value=5, allow_note=True),
        )

    def test_save_config_clears_legacy_review_categories_on_merge(self) -> None:
        from google.cloud import firestore as firestore_sdk

        from lifeguard.features.forms.schema import FormCategory, ScoreOptions
        from lifeguard.modules.content_review import repo
        from lifeguard.modules.content_review.config import ContentReviewConfig

        class FakeDocument:
            def __init__(self, data: dict) -> None:
                self.data = dict(data)

            def set(self, payload: dict, merge: bool = False) -> None:
                if not merge:
                    self.data = dict(payload)
                    return

                merged = dict(self.data)
                for key, value in payload.items():
                    if value is firestore_sdk.DELETE_FIELD:
                        merged.pop(key, None)
                        continue
                    merged[key] = value
                self.data = merged

        class FakeCollection:
            def __init__(self, documents: dict[str, FakeDocument]) -> None:
                self.documents = documents

            def document(self, doc_id: str) -> FakeDocument:
                return self.documents[doc_id]

        class FakeFirestore:
            def __init__(self, documents: dict[str, FakeDocument]) -> None:
                self.documents = documents

            def collection(self, _name: str) -> FakeCollection:
                return FakeCollection(self.documents)

        firestore = FakeFirestore(
            {
                "123": FakeDocument(
                    {
                        "guild_id": 123,
                        "review_categories": [{"id": "legacy", "name": "Legacy"}],
                        "unrelated_setting": "keep-me",
                    }
                )
            }
        )
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

        repo.save_config(firestore, config)

        saved = firestore.documents["123"].data
        self.assertIn("form_categories", saved)
        self.assertNotIn("review_categories", saved)
        self.assertEqual(saved["unrelated_setting"], "keep-me")

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