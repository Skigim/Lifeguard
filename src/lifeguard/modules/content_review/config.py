from __future__ import annotations

from dataclasses import dataclass, field

from lifeguard.features.forms.schema import FormCategory, FormField, ScoreOptions


def _score_options_for_category(category: FormCategory) -> ScoreOptions:
    if isinstance(category.options, ScoreOptions):
        return category.options
    raise TypeError("Content review categories must use score options during migration.")


if not isinstance(getattr(FormCategory, "min_score", None), property):
    FormCategory.min_score = property(
        lambda self: _score_options_for_category(self).min_value
    )
    FormCategory.max_score = property(
        lambda self: _score_options_for_category(self).max_value
    )
    FormCategory.allow_notes = property(
        lambda self: _score_options_for_category(self).allow_note
    )


SubmissionField = FormField


def ReviewCategory(
    *,
    id: str,
    name: str,
    description: str = "",
    min_score: int = 1,
    max_score: int = 5,
    allow_notes: bool = True,
    response_kind: str = "score",
    required: bool = True,
    options: object | None = None,
) -> FormCategory:
    resolved_options = options
    if resolved_options is None and response_kind == "score":
        resolved_options = ScoreOptions(
            min_value=min_score,
            max_value=max_score,
            allow_note=allow_notes,
        )

    return FormCategory(
        id=id,
        name=name,
        description=description,
        response_kind=response_kind,
        required=required,
        options=resolved_options,
    )


def _form_category_from_firestore(data: dict) -> FormCategory:
    if "response_kind" in data or "options" in data:
        return FormCategory.from_firestore(data)

    return ReviewCategory(
        id=data["id"],
        name=data["name"],
        description=data.get("description", ""),
        min_score=data.get("min_score", 1),
        max_score=data.get("max_score", 5),
        allow_notes=data.get("allow_notes", True),
        required=data.get("required", True),
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
    submission_fields: list[FormField] = field(default_factory=list)
    form_categories: list[FormCategory] = field(default_factory=list)
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

    @property
    def review_categories(self) -> list[FormCategory]:
        return self.form_categories

    @review_categories.setter
    def review_categories(self, categories: list[FormCategory]) -> None:
        self.form_categories = list(categories)

    def to_firestore(self) -> dict:
        return {
            "guild_id": self.guild_id,
            "enabled": self.enabled,
            "submission_channel_id": self.submission_channel_id,
            "sticky_message_id": self.sticky_message_id,
            "ticket_category_id": self.ticket_category_id,
            "reviewer_role_ids": self.reviewer_role_ids,
            "submission_fields": [f.to_firestore() for f in self.submission_fields],
            "form_categories": [c.to_firestore() for c in self.form_categories],
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
        raw_form_categories = data.get("form_categories")
        if raw_form_categories is None:
            raw_form_categories = data.get("review_categories", [])

        return cls(
            guild_id=data["guild_id"],
            enabled=data.get("enabled", False),
            submission_channel_id=data.get("submission_channel_id"),
            sticky_message_id=data.get("sticky_message_id"),
            ticket_category_id=data.get("ticket_category_id"),
            reviewer_role_ids=data.get("reviewer_role_ids", []),
            submission_fields=[FormField.from_firestore(f) for f in data.get("submission_fields", [])],
            form_categories=[_form_category_from_firestore(c) for c in raw_form_categories],
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
                FormField(
                    id="game_link",
                    label="Game Link",
                    field_type="url",
                    required=True,
                    placeholder="https://example.com/replay/123",
                ),
                FormField(
                    id="context",
                    label="Context",
                    field_type="short_text",
                    required=False,
                    placeholder="What would you like feedback on?",
                ),
            ],
            form_categories=[
                FormCategory(
                    id="overall",
                    name="Overall",
                    description="How well did the player perform overall?",
                    response_kind="score",
                    options=ScoreOptions(min_value=1, max_value=5, allow_note=True),
                ),
            ],
        )
