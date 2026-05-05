import unittest
from unittest.mock import MagicMock


class FormSessionRepoTests(unittest.TestCase):
    def test_save_session_uses_shared_collection(self) -> None:
        from lifeguard.features.forms.models import FormCategoryResponse, FormResponseSession
        from lifeguard.features.forms.repo import FORMS_SESSIONS_COLLECTION, save_session

        firestore = MagicMock()
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
                    note="Looks good",
                )
            ],
        )

        save_session(firestore, session)

        firestore.collection.assert_called_once_with(FORMS_SESSIONS_COLLECTION)
        firestore.collection.return_value.document.assert_called_once_with("session-1")
        firestore.collection.return_value.document.return_value.set.assert_called_once_with(
            session.to_firestore(),
            merge=True,
        )

    def test_get_session_returns_none_when_document_is_missing(self) -> None:
        from lifeguard.features.forms.repo import get_session

        firestore = MagicMock()
        document = firestore.collection.return_value.document.return_value.get.return_value
        document.exists = False

        session = get_session(firestore, "missing")

        self.assertIsNone(session)

    def test_get_session_restores_firestore_payload(self) -> None:
        from datetime import datetime, timezone

        from lifeguard.features.forms.models import FormCategoryResponse, FormResponseSession
        from lifeguard.features.forms.repo import get_session

        firestore = MagicMock()
        document = firestore.collection.return_value.document.return_value.get.return_value
        document.exists = True
        document.to_dict.return_value = FormResponseSession(
            id="session-2",
            guild_id=123,
            feature_key="content_review",
            owner_id="submission-2",
            responder_id=789,
            responses=[
                FormCategoryResponse(
                    category_id="status",
                    response_kind="single_select",
                    value="ready",
                )
            ],
            status="completed",
            created_at=datetime(2026, 5, 5, 18, 0, tzinfo=timezone.utc),
        ).to_firestore()

        session = get_session(firestore, "session-2")

        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.id, "session-2")
        self.assertEqual(session.responses[0].value, "ready")
        self.assertEqual(session.status, "completed")


if __name__ == "__main__":
    unittest.main()