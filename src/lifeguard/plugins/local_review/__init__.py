"""Local review module and its host registration."""

from lifeguard.config import Settings
from lifeguard.core.plugins import Plugin

from .cog import LocalReviewCog
from .process import LocalReview


def required_intents(settings: Settings) -> tuple[str, ...]:
    return ("message_content",) if settings.environ.get("LOCAL_REVIEW_TOKEN", "").strip() else ()


PLUGIN = Plugin(LocalReview.name, LocalReview, LocalReviewCog, required_intents)
