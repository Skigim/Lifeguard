from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from lifeguard.features.forms.models import FormResponseSession
from lifeguard.features.forms.schema import FormCategory
from lifeguard.modules.content_review.models import ReviewNote


@dataclass
class ReviewPayload:
    scores: dict[str, int] = field(default_factory=dict)
    notes: dict[str, ReviewNote] = field(default_factory=dict)


def _ensure_content_review_score_kind(kind: str, *, context: str) -> None:
    if kind != "score":
        raise ValueError(
            f"Content review {context} must use score responses; got {kind!r}"
        )


def session_to_review_payload(session: FormResponseSession) -> ReviewPayload:
    if session.feature_key != "content_review":
        raise ValueError(
            "Content review translation only supports content_review sessions; "
            f"got {session.feature_key!r}"
        )

    payload = ReviewPayload()
    for response in session.responses:
        _ensure_content_review_score_kind(
            response.response_kind,
            context=f"response category {response.category_id!r}",
        )

        payload.scores[response.category_id] = int(response.value)
        if response.note or response.reference:
            payload.notes[response.category_id] = ReviewNote(
                reference=response.reference,
                feedback=response.note,
            )
    return payload


def build_review_session_draft(
    submission_id: str,
    guild_id: int,
    responder_id: int,
    categories: Sequence[FormCategory],
) -> FormResponseSession:
    for category in categories:
        _ensure_content_review_score_kind(
            category.response_kind,
            context=f"category {category.id!r}",
        )

    return FormResponseSession(
        id=f"content_review:{submission_id}:{responder_id}",
        guild_id=guild_id,
        feature_key="content_review",
        owner_id=submission_id,
        responder_id=responder_id,
        responses=[],
        status="draft",
    )