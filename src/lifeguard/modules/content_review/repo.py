"""Firestore repository for Content Review module."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from lifeguard.modules.content_review.config import ContentReviewConfig
from lifeguard.modules.content_review.models import (
    ReviewSession,
    Submission,
    UserProfile,
)

if TYPE_CHECKING:
    from google.cloud.firestore import Client as FirestoreClient


# Collection names
CONFIGS_COLLECTION = "content_review_configs"
SUBMISSIONS_COLLECTION = "content_review_submissions"
REVIEWS_COLLECTION = "content_review_reviews"
PROFILES_COLLECTION = "content_review_profiles"


def _guild_doc_id(guild_id: int) -> str:
    """Generate document ID for guild-level documents."""
    return str(guild_id)


def _profile_doc_id(guild_id: int, user_id: int) -> str:
    """Generate document ID for user profile documents."""
    return f"{guild_id}_{user_id}"


def _generate_id() -> str:
    """Generate a unique document ID."""
    return uuid.uuid4().hex[:16]


# --- Config CRUD ---


def get_config(firestore: FirestoreClient, guild_id: int) -> ContentReviewConfig | None:
    """Get the content review configuration for a guild."""
    doc = firestore.collection(CONFIGS_COLLECTION).document(_guild_doc_id(guild_id)).get()
    if not doc.exists:
        return None
    return ContentReviewConfig.from_firestore(doc.to_dict())


def save_config(firestore: FirestoreClient, config: ContentReviewConfig) -> None:
    """Save or update a guild's content review configuration."""
    firestore.collection(CONFIGS_COLLECTION).document(
        _guild_doc_id(config.guild_id)
    ).set(config.to_firestore(), merge=True)


def delete_config(firestore: FirestoreClient, guild_id: int) -> None:
    """Delete a guild's content review configuration."""
    firestore.collection(CONFIGS_COLLECTION).document(_guild_doc_id(guild_id)).delete()


def get_or_create_config(firestore: FirestoreClient, guild_id: int) -> ContentReviewConfig:
    """Get existing config or create a default one."""
    config = get_config(firestore, guild_id)
    if config is None:
        config = ContentReviewConfig.default(guild_id)
        save_config(firestore, config)
    return config


# --- Submission CRUD ---


def create_submission(firestore: FirestoreClient, submission: Submission) -> str:
    """Create a new submission and return its ID."""
    if not submission.id:
        submission.id = _generate_id()
    firestore.collection(SUBMISSIONS_COLLECTION).document(submission.id).set(
        submission.to_firestore()
    )
    return submission.id


def get_submission(firestore: FirestoreClient, submission_id: str) -> Submission | None:
    """Get a submission by ID."""
    doc = firestore.collection(SUBMISSIONS_COLLECTION).document(submission_id).get()
    if not doc.exists:
        return None
    return Submission.from_firestore(doc.to_dict())


def update_submission(firestore: FirestoreClient, submission: Submission) -> None:
    """Update an existing submission."""
    firestore.collection(SUBMISSIONS_COLLECTION).document(submission.id).set(
        submission.to_firestore(), merge=True
    )


def get_submission_by_channel(
    firestore: FirestoreClient, guild_id: int, channel_id: int
) -> Submission | None:
    """Get a submission by its ticket channel ID."""
    docs = (
        firestore.collection(SUBMISSIONS_COLLECTION)
        .where("guild_id", "==", guild_id)
        .where("channel_id", "==", channel_id)
        .limit(1)
        .get()
    )
    for doc in docs:
        return Submission.from_firestore(doc.to_dict())
    return None


def get_pending_submissions(
    firestore: FirestoreClient, guild_id: int, limit: int = 50
) -> list[Submission]:
    """Get pending submissions for a guild."""
    docs = (
        firestore.collection(SUBMISSIONS_COLLECTION)
        .where("guild_id", "==", guild_id)
        .where("status", "==", "pending")
        .order_by("created_at")
        .limit(limit)
        .stream()
    )
    return [Submission.from_firestore(doc.to_dict()) for doc in docs]


# --- Review CRUD ---


def create_review(firestore: FirestoreClient, review: ReviewSession) -> str:
    """Create a new review session and return its ID."""
    if not review.id:
        review.id = _generate_id()
    firestore.collection(REVIEWS_COLLECTION).document(review.id).set(
        review.to_firestore()
    )
    return review.id


def get_review(firestore: FirestoreClient, review_id: str) -> ReviewSession | None:
    """Get a review by ID."""
    doc = firestore.collection(REVIEWS_COLLECTION).document(review_id).get()
    if not doc.exists:
        return None
    return ReviewSession.from_firestore(doc.to_dict())


def get_reviews_for_submission(
    firestore: FirestoreClient, submission_id: str
) -> list[ReviewSession]:
    """Get all reviews for a submission."""
    docs = (
        firestore.collection(REVIEWS_COLLECTION)
        .where("submission_id", "==", submission_id)
        .stream()
    )
    return [ReviewSession.from_firestore(doc.to_dict()) for doc in docs]


def get_reviews_by_reviewer(
    firestore: FirestoreClient, guild_id: int, reviewer_id: int, limit: int = 50
) -> list[ReviewSession]:
    """Get reviews given by a specific reviewer."""
    docs = (
        firestore.collection(REVIEWS_COLLECTION)
        .where("guild_id", "==", guild_id)
        .where("reviewer_id", "==", reviewer_id)
        .order_by("completed_at")
        .limit(limit)
        .stream()
    )
    return [ReviewSession.from_firestore(doc.to_dict()) for doc in docs]


# --- User Profile CRUD ---


def get_profile(
    firestore: FirestoreClient, guild_id: int, user_id: int
) -> UserProfile | None:
    """Get a user's profile for a guild."""
    doc = (
        firestore.collection(PROFILES_COLLECTION)
        .document(_profile_doc_id(guild_id, user_id))
        .get()
    )
    if not doc.exists:
        return None
    return UserProfile.from_firestore(doc.to_dict())


def save_profile(firestore: FirestoreClient, profile: UserProfile) -> None:
    """Save or update a user's profile."""
    firestore.collection(PROFILES_COLLECTION).document(
        _profile_doc_id(profile.guild_id, profile.user_id)
    ).set(profile.to_firestore(), merge=True)


def get_or_create_profile(
    firestore: FirestoreClient, guild_id: int, user_id: int
) -> UserProfile:
    """Get existing profile or create a new one."""
    profile = get_profile(firestore, guild_id, user_id)
    if profile is None:
        profile = UserProfile(user_id=user_id, guild_id=guild_id)
        save_profile(firestore, profile)
    return profile


def get_leaderboard(
    firestore: FirestoreClient, guild_id: int, limit: int = 10
) -> list[UserProfile]:
    """Get top reviewers by number of reviews given."""
    docs = (
        firestore.collection(PROFILES_COLLECTION)
        .where("guild_id", "==", guild_id)
        .where("total_reviews_given", ">", 0)
        .order_by("total_reviews_given", direction="DESCENDING")
        .limit(limit)
        .stream()
    )
    return [UserProfile.from_firestore(doc.to_dict()) for doc in docs]
