from __future__ import annotations

from datetime import datetime, timezone
import unittest


class _FakeTimestamp:
    def __init__(self, value: datetime) -> None:
        self._value = value

    def to_datetime(self) -> datetime:
        return self._value


class FormSessionModelTests(unittest.TestCase):
    def test_form_category_response_round_trips_supported_kinds(self) -> None:
        from lifeguard.features.forms.models import FormCategoryResponse

        cases = [
            FormCategoryResponse(
                category_id="overall",
                response_kind="score",
                value=4,
                note="Strong fundamentals",
                reference="01:20",
            ),
            FormCategoryResponse(
                category_id="summary",
                response_kind="note",
                value="Needs more detail",
                reference="clip-3",
            ),
            FormCategoryResponse(
                category_id="context",
                response_kind="text",
                value="Handled the reset well.",
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
                value=["clear", "supportive"],
            ),
        ]

        for response in cases:
            with self.subTest(response_kind=response.response_kind):
                restored = FormCategoryResponse.from_firestore(response.to_firestore())

                self.assertEqual(restored.category_id, response.category_id)
                self.assertEqual(restored.response_kind, response.response_kind)
                self.assertEqual(restored.value, response.value)
                self.assertEqual(restored.note, response.note)
                self.assertEqual(restored.reference, response.reference)

    def test_form_response_session_round_trips_firestore_timestamps(self) -> None:
        from lifeguard.features.forms.models import FormCategoryResponse, FormResponseSession

        created_at = datetime(2026, 5, 5, 18, 30, tzinfo=timezone.utc)
        completed_at = datetime(2026, 5, 5, 18, 45, tzinfo=timezone.utc)
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
                    value=5,
                    note="Ready to publish",
                    reference="02:10",
                ),
                FormCategoryResponse(
                    category_id="tags",
                    response_kind="multi_select",
                    value=["clear", "concise"],
                ),
            ],
            status="completed",
            created_at=created_at,
            completed_at=completed_at,
        )

        payload = session.to_firestore()
        payload["created_at"] = _FakeTimestamp(created_at)
        payload["completed_at"] = _FakeTimestamp(completed_at)

        restored = FormResponseSession.from_firestore(payload)

        self.assertEqual(restored.id, "session-1")
        self.assertEqual(restored.feature_key, "content_review")
        self.assertEqual(restored.status, "completed")
        self.assertEqual(restored.created_at, created_at)
        self.assertEqual(restored.completed_at, completed_at)
        self.assertEqual(restored.responses[0].note, "Ready to publish")
        self.assertEqual(restored.responses[0].reference, "02:10")
        self.assertEqual(restored.responses[1].value, ["clear", "concise"])


if __name__ == "__main__":
    unittest.main()