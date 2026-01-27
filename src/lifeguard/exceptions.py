"""Shared exceptions for Lifeguard modules."""

from __future__ import annotations

from discord import app_commands


class FeatureDisabledError(app_commands.CheckFailure):
    """Raised when a feature is disabled for a guild.
    
    Used by feature check decorators to signal that a command
    cannot be executed because the required feature is not enabled.
    """
    
    def __init__(self, feature_name: str) -> None:
        self.feature_name = feature_name
        super().__init__(f"{feature_name} is not enabled in this server.")
