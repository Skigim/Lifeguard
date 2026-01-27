from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Literal

from lifeguard.utils import drop_none


@dataclass
class ReviewNote:
    """A note attached to a specific category in a review."""

    reference: str  # Timestamp, section, or context reference
    feedback: str  # The actual feedback text

    def to_firestore(self) -> dict:
        return asdict(self)

    @classmethod
    def from_firestore(cls, data: dict) -> ReviewNote:
        return cls(
            reference=data.get("reference", ""),
            feedback=data.get("feedback", ""),
        )


@dataclass
class Submission:
    """A user submission awaiting review."""

    id: str
    guild_id: int
    channel_id: int  # The ticket channel created for this submission
    message_id: int
    submitter_id: int
    fields: dict[str, str]  # field_id -> value
    status: Literal["pending", "in_review", "completed", "closed"] = "pending"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reviewer_id: int | None = None  # Set when someone starts reviewing

    def to_firestore(self) -> dict:
        return {
            "id": self.id,
            "guild_id": self.guild_id,
            "channel_id": self.channel_id,
            "message_id": self.message_id,
            "submitter_id": self.submitter_id,
            "fields": self.fields,
            "status": self.status,
            "created_at": self.created_at,
            "reviewer_id": self.reviewer_id,
        }

    @classmethod
    def from_firestore(cls, data: dict) -> Submission:
        created_at = data.get("created_at")
        if isinstance(created_at, datetime):
            pass
        elif created_at is not None:
            created_at = created_at.to_datetime()  # Firestore Timestamp
        else:
            created_at = datetime.now(timezone.utc)

        return cls(
            id=data["id"],
            guild_id=data["guild_id"],
            channel_id=data["channel_id"],
            message_id=data["message_id"],
            submitter_id=data["submitter_id"],
            fields=data.get("fields", {}),
            status=data.get("status", "pending"),
            created_at=created_at,
            reviewer_id=data.get("reviewer_id"),
        )


@dataclass
class ReviewSession:
    """A completed review of a submission."""

    id: str
    submission_id: str
    guild_id: int
    reviewer_id: int
    submitter_id: int
    scores: dict[str, int]  # category_id -> score
    notes: dict[str, ReviewNote]  # category_id -> note
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None

    def to_firestore(self) -> dict:
        return {
            "id": self.id,
            "submission_id": self.submission_id,
            "guild_id": self.guild_id,
            "reviewer_id": self.reviewer_id,
            "submitter_id": self.submitter_id,
            "scores": self.scores,
            "notes": {k: v.to_firestore() for k, v in self.notes.items()},
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_firestore(cls, data: dict) -> ReviewSession:
        def parse_datetime(val):
            if val is None:
                return None
            if isinstance(val, datetime):
                return val
            return val.to_datetime()  # Firestore Timestamp

        return cls(
            id=data["id"],
            submission_id=data["submission_id"],
            guild_id=data["guild_id"],
            reviewer_id=data["reviewer_id"],
            submitter_id=data["submitter_id"],
            scores=data.get("scores", {}),
            notes={
                k: ReviewNote.from_firestore(v)
                for k, v in data.get("notes", {}).items()
            },
            created_at=parse_datetime(data.get("created_at")) or datetime.now(timezone.utc),
            completed_at=parse_datetime(data.get("completed_at")),
        )

    def average_score(self) -> float:
        """Calculate the average score across all categories."""
        if not self.scores:
            return 0.0
        return sum(self.scores.values()) / len(self.scores)


@dataclass
class SubmissionSummary:
    """Lightweight summary of a submission for history lists."""

    submission_id: str
    average_score: float
    date: datetime

    def to_firestore(self) -> dict:
        return asdict(self)

    @classmethod
    def from_firestore(cls, data: dict) -> SubmissionSummary:
        date = data.get("date")
        if isinstance(date, datetime):
            pass
        elif date is not None:
            date = date.to_datetime()
        else:
            date = datetime.now(timezone.utc)

        return cls(
            submission_id=data["submission_id"],
            average_score=data.get("average_score", 0.0),
            date=date,
        )


@dataclass
class UserProfile:
    """Tracks a user's submission and review statistics."""

    user_id: int
    guild_id: int
    total_submissions: int = 0
    total_reviews_given: int = 0
    average_score: float = 0.0  # Running average across all submissions
    category_averages: dict[str, float] = field(default_factory=dict)  # category_id -> avg
    badges: list[str] = field(default_factory=list)
    submission_history: list[SubmissionSummary] = field(default_factory=list)

    def to_firestore(self) -> dict:
        return {
            "user_id": self.user_id,
            "guild_id": self.guild_id,
            "total_submissions": self.total_submissions,
            "total_reviews_given": self.total_reviews_given,
            "average_score": self.average_score,
            "category_averages": self.category_averages,
            "badges": self.badges,
            "submission_history": [s.to_firestore() for s in self.submission_history],
        }

    @classmethod
    def from_firestore(cls, data: dict) -> UserProfile:
        return cls(
            user_id=data["user_id"],
            guild_id=data["guild_id"],
            total_submissions=data.get("total_submissions", 0),
            total_reviews_given=data.get("total_reviews_given", 0),
            average_score=data.get("average_score", 0.0),
            category_averages=data.get("category_averages", {}),
            badges=data.get("badges", []),
            submission_history=[
                SubmissionSummary.from_firestore(s)
                for s in data.get("submission_history", [])
            ],
        )

    def update_with_review(self, review: ReviewSession) -> None:
        """Update profile statistics with a new review."""
        self.total_submissions += 1
        avg = review.average_score()

        # Update running average
        if self.total_submissions == 1:
            self.average_score = avg
        else:
            # Incremental average: new_avg = old_avg + (new_val - old_avg) / n
            self.average_score += (avg - self.average_score) / self.total_submissions

        # Update per-category averages
        for cat_id, score in review.scores.items():
            if cat_id not in self.category_averages:
                self.category_averages[cat_id] = float(score)
            else:
                # Simple running average per category
                old_avg = self.category_averages[cat_id]
                # Approximate - assumes equal submissions per category
                self.category_averages[cat_id] = old_avg + (score - old_avg) / self.total_submissions

        # Add to history
        self.submission_history.append(
            SubmissionSummary(
                submission_id=review.submission_id,
                average_score=avg,
                date=review.completed_at or datetime.now(timezone.utc),
            )
        )
