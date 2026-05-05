import unittest

from lifeguard.features.forms.models import FormCategoryResponse, FormResponseSession
from lifeguard.features.forms.schema import FormCategory, ScoreOptions


class ContentReviewFormsTranslationTests(unittest.TestCase):
    def test_score_session_translates_to_review_payload(self) -> None:
        from lifeguard.modules.content_review.forms_translation import session_to_review_payload

        session = FormResponseSession(
            id="session-1",
            guild_id=123,
            feature_key="content_review",
            owner_id="submission-1",
            responder_id=456,
            responses=[
                FormCategoryResponse(
                    category_id="overall",
                    response_kind="score",
                    value=4,
                    note="Solid progress",
                    reference="01:23",
                )
            ],
            status="completed",
        )

        payload = session_to_review_payload(session)

        self.assertEqual(payload.scores, {"overall": 4})
        self.assertEqual(payload.notes["overall"].feedback, "Solid progress")
        self.assertEqual(payload.notes["overall"].reference, "01:23")

    def test_build_review_session_draft_sets_content_review_defaults(self) -> None:
        from lifeguard.modules.content_review.forms_translation import build_review_session_draft

        categories = [
            FormCategory(
                id="overall",
                name="Overall",
                response_kind="score",
                options=ScoreOptions(),
            ),
            FormCategory(
                id="teamplay",
                name="Teamplay",
                response_kind="score",
                options=ScoreOptions(),
            ),
        ]

        draft = build_review_session_draft(
            submission_id="submission-1",
            guild_id=123,
            responder_id=456,
            categories=categories,
        )

        self.assertEqual(draft.feature_key, "content_review")
        self.assertEqual(draft.owner_id, "submission-1")
        self.assertEqual(draft.guild_id, 123)
        self.assertEqual(draft.responder_id, 456)
        self.assertEqual(draft.responses, [])
        self.assertEqual(draft.status, "draft")
        self.assertEqual([category.id for category in categories], ["overall", "teamplay"])


if __name__ == "__main__":
    unittest.main()