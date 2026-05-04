from __future__ import annotations

from discord.ext import commands

from lifeguard.features.adapters import StatusMenuConfigAdapter
from lifeguard.modules.time_impersonator.cog import TimeImpersonatorCog
from lifeguard.modules.time_impersonator.views.config_ui import (
    TimeImpersonatorConfigView,
)


class TimeImpersonatorConfigAdapter(
    StatusMenuConfigAdapter[TimeImpersonatorCog, TimeImpersonatorConfigView]
):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(
            bot,
            cog_name="TimeImpersonatorCog",
            missing_cog_message="TimeImpersonatorCog is not loaded",
            missing_callback_message="Time Impersonator config requires a home callback",
        )

    def build_menu_view(self) -> TimeImpersonatorConfigView:
        return TimeImpersonatorConfigView(
            self,
            on_back_to_home=self._require_on_back_to_home(),
        )
