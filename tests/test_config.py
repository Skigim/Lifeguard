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


def test_optional_github_settings_and_private_key_file(tmp_path):
    key = tmp_path / "key.pem"
    key.write_text("private-key")
    env = {
        "DISCORD_TOKEN": "x",
        "DATABASE_PATH": "data/bot.db",
        "GITHUB_APP_ID": "1",
        "GITHUB_APP_PRIVATE_KEY_PATH": str(key),
        "GITHUB_WEBHOOK_SECRET": "secret",
        "GITHUB_CLIENT_ID": "client",
        "GITHUB_CLIENT_SECRET": "secret",
        "PUBLIC_URL": "https://example.com/",
        "TOKEN_ENCRYPTION_KEY": "key",
    }
    settings = load_settings(env)
    assert settings.github.private_key == "private-key"
    assert settings.github.web_port == 8080
    assert settings.github.public_url == "https://example.com"
    assert settings.database_path == "data/bot.db"
    with pytest.raises(ConfigError, match="WEB_PORT"):
        load_settings(dict(env, WEB_PORT="invalid"))
    with pytest.raises(ConfigError, match="HTTPS"):
        load_settings(dict(env, PUBLIC_URL="http://example.com"))
