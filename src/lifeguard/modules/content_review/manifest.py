from __future__ import annotations

from lifeguard.features.contracts import FeatureManifest
from lifeguard.modules.content_review.cog import ContentReviewCog
from lifeguard.modules.content_review.config_adapter import ContentReviewConfigAdapter


FEATURE_MANIFEST = FeatureManifest(
    feature_key="content_review",
    display_name="Content Review",
    description="Review system with tickets, scoring, and leaderboards",
    emoji="📝",
    requires_setup=True,
    cog_name="ContentReviewCog",
    load_cog=lambda bot: ContentReviewCog(bot),
    build_adapter=lambda bot: ContentReviewConfigAdapter(bot),
)
