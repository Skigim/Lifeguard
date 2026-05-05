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


def session_to_review_payload(session: FormResponseSession) -> ReviewPayload:
    payload = ReviewPayload()
    for response in session.responses:
        if response.response_kind != "score":
            continue

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
    # Materialize the sequence to keep later callers free to pass any ordered iterable
    # without this helper mutating or consuming the source unexpectedly.
    tuple(categories)
    return FormResponseSession(
        id=f"content_review:{submission_id}:{responder_id}",
        guild_id=guild_id,
        feature_key="content_review",
        owner_id=submission_id,
        responder_id=responder_id,
        responses=[],
        status="draft",
    )