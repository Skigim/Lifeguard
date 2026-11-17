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
    assert {
        "bridge link-repo",
        "bridge unlink-repo",
        "bridge repos",
        "bridge backfill",
        "bridge map-label",
        "bridge bot-login add",
        "bridge bot-login remove",
        "github link",
        "github unlink",
        "github whoami",
        "comment",
        "close",
        "reopen",
    } <= command_paths(bot)
    menus = bot.tree.get_commands(type=discord.AppCommandType.message)
    assert {menu.name for menu in menus} == {"Edit on GitHub", "Delete on GitHub"}


async def test_feature_group_requires_manage_guild(bot):
    group = bot.tree.get_command("feature")
    assert group.guild_only is True
    assert group.default_permissions.manage_guild is True
    bridge = bot.tree.get_command("bridge")
    assert bridge.guild_only and bridge.default_permissions.manage_guild


async def test_github_missing_config_is_friendly(bot):
    from lifeguard.core.loader import ProcessStartFailed

    with pytest.raises(ProcessStartFailed) as caught:
        await bot.loader.enable("github", 1)
    interaction = FakeInteraction()
    await on_app_command_error(interaction, caught.value)
    assert "Couldn't start `github`" in interaction.response.sent[0]
    assert not bot.loader.is_enabled("github", 1)


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


async def test_help_autocompletes_features_and_links_the_doc(bot):
    command = bot.tree.get_command("help")
    assert command.parameters[0].name == "feature"
    assert command.parameters[0].autocomplete
    interaction = FakeInteraction()
    choices = await command.binding.help_features(interaction, "GIT")
    assert [choice.value for choice in choices] == ["github"]
    await command.callback(command.binding, interaction, choices[0].value)
    message, ephemeral = interaction.response.sent
    assert "https://github.com/Skigim/Lifeguard/blob/main/docs/features/github.md" in message
    assert ephemeral
    await command.callback(command.binding, interaction, "unknown")
    assert interaction.response.sent[0].startswith("Unknown feature.")
