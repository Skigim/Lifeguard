from lifeguard.core.db import MIGRATIONS, SqliteEnablementStore


def test_enablement_survives_restart(tmp_path):
    path = str(tmp_path / "nested" / "bot.db")
    store = SqliteEnablementStore(path)
    store.add("github", 1)
    store.add("github", 1)
    store.add("greeter", 2)
    store.close()
    store = SqliteEnablementStore(path)
    assert store.guilds_for("github") == {1}
    store.remove("github", 1)
    assert store.guilds_for("github") == set()
    assert store.guilds_for("greeter") == {2}
    assert store.db.execute("SELECT version FROM schema_version").fetchone()[0] == len(MIGRATIONS)
    store.close()
