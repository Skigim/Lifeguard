from __future__ import annotations

from lifeguard.features.contracts import FeatureManifest
from lifeguard.modules.voice_lobby.cog import VoiceLobbyCog
from lifeguard.modules.voice_lobby.config_adapter import VoiceLobbyConfigAdapter


FEATURE_MANIFEST = FeatureManifest(
    feature_key="voice_lobby",
    display_name="Voice Lobby",
    description="Temporary voice lobbies created from an entry channel",
    emoji="🎧",
    requires_setup=False,
    cog_name="VoiceLobbyCog",
    load_cog=lambda bot: VoiceLobbyCog(bot),
    build_adapter=lambda bot: VoiceLobbyConfigAdapter(bot),
)
