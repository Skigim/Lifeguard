from types import SimpleNamespace

import discord
import pytest

from lifeguard.bot import DISABLED_MESSAGE, LifeguardBot, on_app_command_error
from lifeguard.config import Settings
from lifeguard.core.loader import ProcessDisabled
from lifeguard.core.process import ProcessState
from lifeguard.features.greeter import Greeter


@pytest.fixture
async def bot():
    b = LifeguardBot(Settings(env="test", token="x"))
    await b.load_features()
    yield b
    await b.loader.shutdown()


def command_paths(bot: LifeguardBot) -> set[str]:
    return {c.qualified_name for c in bot.tree.walk_commands()}


async def test_commands_registered(bot):
    assert {"ping", "greet", "feature enable", "feature disable", "feature list"} <= command_paths(
        bot
    )


async def test_feature_group_requires_manage_guild(bot):
    group = bot.tree.get_command("feature")
    assert group.guild_only is True
    assert group.default_permissions.manage_guild is True


async def test_enable_disable_cycle(bot):
    loader = bot.loader
    assert loader.state("greeter") is ProcessState.STOPPED
    with pytest.raises(ProcessDisabled):
        loader.require("greeter", 1)

    await loader.enable("greeter", 1)
    proc = loader.require("greeter", 1)
    assert isinstance(proc, Greeter)
    assert proc.greet("Ann").endswith("#1 since this feature started)")
    assert proc.greet("Ann").endswith("#2 since this feature started)")

    # another guild stays gated
    with pytest.raises(ProcessDisabled):
        loader.require("greeter", 2)

    await loader.disable("greeter", 1)
    assert loader.state("greeter") is ProcessState.STOPPED
    with pytest.raises(ProcessDisabled):
        loader.require("greeter", 1)

    # re-enabling gives a fresh process: counter restarts
    await loader.enable("greeter", 1)
    assert loader.require("greeter", 1).greet("Ann").endswith("#1 since this feature started)")


class FakeResponse:
    def __init__(self):
        self.sent = None

    def is_done(self):
        return False

    async def send_message(self, message, ephemeral=False):
        self.sent = (message, ephemeral)


class FakeInteraction:
    def __init__(self):
        self.response = FakeResponse()


async def test_disabled_error_becomes_friendly_message():
    interaction = FakeInteraction()
    command = SimpleNamespace(name="greet")
    error = discord.app_commands.CommandInvokeError(command, ProcessDisabled("x"))  # type: ignore[arg-type]
    await on_app_command_error(interaction, error)  # type: ignore[arg-type]
    assert interaction.response.sent == (DISABLED_MESSAGE, True)
