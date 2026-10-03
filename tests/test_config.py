import pytest

from lifeguard.cogs.core import format_latency
from lifeguard.config import ConfigError, load_settings


def test_defaults_to_test_env():
    s = load_settings({"DISCORD_TOKEN": "x"})
    assert s.env == "test"
    assert not s.is_production
    assert s.guild_id is None


def test_production_is_opt_in():
    s = load_settings({"DISCORD_TOKEN": "x", "BOT_ENV": "Production"})
    assert s.is_production


def test_guild_id_parsed():
    assert load_settings({"DISCORD_TOKEN": "x", "GUILD_ID": "42"}).guild_id == 42


@pytest.mark.parametrize(
    "env",
    [
        {},
        {"DISCORD_TOKEN": "  "},
        {"DISCORD_TOKEN": "x", "BOT_ENV": "staging"},
        {"DISCORD_TOKEN": "x", "GUILD_ID": "abc"},
    ],
)
def test_invalid_config_raises(env):
    with pytest.raises(ConfigError):
        load_settings(env)


def test_format_latency():
    assert format_latency(0.0426) == "Pong! 43 ms"
