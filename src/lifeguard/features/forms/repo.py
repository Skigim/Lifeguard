from __future__ import annotations

from typing import TYPE_CHECKING

from lifeguard.features.forms.models import FormResponseSession

if TYPE_CHECKING:
    from google.cloud.firestore import Client as FirestoreClient


FORMS_SESSIONS_COLLECTION = "forms_response_sessions"


def save_session(firestore: FirestoreClient, session: FormResponseSession) -> None:
    firestore.collection(FORMS_SESSIONS_COLLECTION).document(session.id).set(
        session.to_firestore(),
        merge=True,
    )


def get_session(
    firestore: FirestoreClient,
    session_id: str,
) -> FormResponseSession | None:
    document = firestore.collection(FORMS_SESSIONS_COLLECTION).document(session_id).get()
    if not document.exists:
        return None
    return FormResponseSession.from_firestore(document.to_dict())