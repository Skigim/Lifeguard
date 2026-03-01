from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

from lifeguard.utils import drop_none


@dataclass(frozen=True)
class ReviewCategory:
    """Defines a single category that reviewers will score."""

    id: str  # Unique identifier (e.g., "communication")
    name: str  # Display name (e.g., "Communication")
    description: str = ""  # Tooltip/help text
    min_score: int = 1  # Minimum rating value
    max_score: int = 5  # Maximum rating value
    allow_notes: bool = True  # Whether reviewers can add notes

    def to_firestore(self) -> dict:
        return drop_none(asdict(self))

    @classmethod
    def from_firestore(cls, data: dict) -> ReviewCategory:
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            min_score=data.get("min_score", 1),
            max_score=data.get("max_score", 5),
            allow_notes=data.get("allow_notes", True),
        )


@dataclass(frozen=True)
class SubmissionField:
    """Defines a single input field in the submission modal."""

    id: str  # Unique identifier
    label: str  # Display label
    field_type: Literal["short_text", "paragraph", "url"] = "short_text"
    required: bool = True
    placeholder: str = ""
    validation_regex: str = ""  # Optional regex for validation

    def to_firestore(self) -> dict:
        return drop_none(asdict(self))

    @classmethod
    def from_firestore(cls, data: dict) -> SubmissionField:
        return cls(
            id=data["id"],
            label=data["label"],
            field_type=data.get("field_type", "short_text"),
            required=data.get("required", True),
            placeholder=data.get("placeholder", ""),
            validation_regex=data.get("validation_regex", ""),
        )


@dataclass
class ContentReviewConfig:
    """Per-guild configuration for the content review module."""

    guild_id: int
    enabled: bool = False
    submission_channel_id: int | None = None  # Where the submit button is posted
    sticky_message_id: int | None = None  # The pinned submit button message
    ticket_category_id: int | None = None  # Category where ticket channels are created
    reviewer_role_ids: list[int] = field(
        default_factory=list
    )  # Roles allowed to review
    submission_fields: list[SubmissionField] = field(default_factory=list)
    review_categories: list[ReviewCategory] = field(default_factory=list)
    dm_on_complete: bool = True  # DM submitter when review is done
    leaderboard_enabled: bool = True
    review_timeout_minutes: int = 15  # How long before draft reviews expire

    # Sticky message customization
    sticky_title: str = "📥 Content Review"
    sticky_description: str = (
        "Submit your content for feedback from the community!\n\n"
        "Click the button below to open the submission form."
    )
    sticky_button_label: str = "Submit Content"
    sticky_button_emoji: str = "📝"

    # Submission modal customization
    modal_title: str = "Submit for Review"

    # Ticket embed customization (supports {user}, {submission_id} placeholders)
    ticket_title: str = "Review Request from {user}"
    ticket_description: str = "A new submission is ready for review."

    def to_firestore(self) -> dict:
        return {
            "guild_id": self.guild_id,
            "enabled": self.enabled,
            "submission_channel_id": self.submission_channel_id,
            "sticky_message_id": self.sticky_message_id,
            "ticket_category_id": self.ticket_category_id,
            "reviewer_role_ids": self.reviewer_role_ids,
            "submission_fields": [f.to_firestore() for f in self.submission_fields],
            "review_categories": [c.to_firestore() for c in self.review_categories],
            "dm_on_complete": self.dm_on_complete,
            "leaderboard_enabled": self.leaderboard_enabled,
            "review_timeout_minutes": self.review_timeout_minutes,
            "sticky_title": self.sticky_title,
            "sticky_description": self.sticky_description,
            "sticky_button_label": self.sticky_button_label,
            "sticky_button_emoji": self.sticky_button_emoji,
            "modal_title": self.modal_title,
            "ticket_title": self.ticket_title,
            "ticket_description": self.ticket_description,
        }

    @classmethod
    def from_firestore(cls, data: dict) -> ContentReviewConfig:
        return cls(
            guild_id=data["guild_id"],
            enabled=data.get("enabled", False),
            submission_channel_id=data.get("submission_channel_id"),
            sticky_message_id=data.get("sticky_message_id"),
            ticket_category_id=data.get("ticket_category_id"),
            reviewer_role_ids=data.get("reviewer_role_ids", []),
            submission_fields=[
                SubmissionField.from_firestore(f)
                for f in data.get("submission_fields", [])
            ],
            review_categories=[
                ReviewCategory.from_firestore(c)
                for c in data.get("review_categories", [])
            ],
            dm_on_complete=data.get("dm_on_complete", True),
            leaderboard_enabled=data.get("leaderboard_enabled", True),
            review_timeout_minutes=data.get("review_timeout_minutes", 15),
            sticky_title=data.get("sticky_title", "📥 Content Review"),
            sticky_description=data.get(
                "sticky_description",
                "Submit your content for feedback from the community!\n\n"
                "Click the button below to open the submission form.",
            ),
            sticky_button_label=data.get("sticky_button_label", "Submit Content"),
            sticky_button_emoji=data.get("sticky_button_emoji", "📝"),
            modal_title=data.get("modal_title", "Submit for Review"),
            ticket_title=data.get("ticket_title", "Review Request from {user}"),
            ticket_description=data.get(
                "ticket_description", "A new submission is ready for review."
            ),
        )

    @classmethod
    def default(cls, guild_id: int) -> ContentReviewConfig:
        """Create a default configuration for basic game review."""
        return cls(
            guild_id=guild_id,
            enabled=False,
            submission_fields=[
                SubmissionField(
                    id="game_link",
                    label="Game Link",
                    field_type="url",
                    required=True,
                    placeholder="https://example.com/replay/123",
                ),
                SubmissionField(
                    id="context",
                    label="Context",
                    field_type="short_text",
                    required=False,
                    placeholder="What would you like feedback on?",
                ),
            ],
            review_categories=[
                ReviewCategory(
                    id="overall",
                    name="Overall",
                    description="How well did the player perform overall?",
                    min_score=1,
                    max_score=5,
                    allow_notes=True,
                ),
            ],
        )
