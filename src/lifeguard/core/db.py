"""Ordered, transactional SQLite migrations shared by the core and features."""

import sqlite3
from contextlib import closing
from pathlib import Path

USER_TIMEZONES_SCHEMA = """
CREATE TABLE user_timezones(discord_id INTEGER PRIMARY KEY, zone TEXT NOT NULL);
"""

MIGRATIONS = (
    """
    CREATE TABLE enablement(name TEXT, guild_id INTEGER, PRIMARY KEY(name, guild_id));
    CREATE TABLE repo_links(guild_id INTEGER, repo TEXT, forum_id INTEGER,
      installation_id INTEGER, PRIMARY KEY(guild_id, repo));
    CREATE TABLE posts(guild_id INTEGER, repo TEXT, number INTEGER, kind TEXT,
      thread_id INTEGER, starter_msg_id INTEGER, state TEXT,
      PRIMARY KEY(guild_id, repo, number));
    CREATE TABLE comments(guild_id INTEGER, repo TEXT, number INTEGER, gh_comment_id INTEGER,
      gh_kind TEXT, gh_author_id INTEGER, thread_id INTEGER, message_id INTEGER, collapsed INTEGER,
      PRIMARY KEY(guild_id, repo, gh_kind, gh_comment_id));
    CREATE INDEX comments_message ON comments(guild_id, message_id);
    CREATE TABLE label_tags(forum_id INTEGER, label TEXT, tag_id INTEGER,
      PRIMARY KEY(forum_id, label));
    CREATE TABLE bot_logins(guild_id INTEGER, login TEXT, mode TEXT,
      PRIMARY KEY(guild_id, login));
    CREATE TABLE user_links(discord_id INTEGER PRIMARY KEY, gh_id INTEGER, gh_login TEXT,
      access_enc TEXT, refresh_enc TEXT, access_exp REAL, refresh_exp REAL);
    CREATE TABLE oauth_states(state TEXT PRIMARY KEY, discord_id INTEGER, created_at REAL);
    CREATE TABLE deliveries(delivery_id TEXT PRIMARY KEY, received_at REAL, processed_at REAL);
    CREATE TABLE bridge_state(key TEXT PRIMARY KEY, value TEXT);
    """,
    """
    ALTER TABLE comments ADD COLUMN activity_text TEXT;
    ALTER TABLE comments ADD COLUMN activity_url TEXT;
    ALTER TABLE comments ADD COLUMN activity_at TEXT;
    ALTER TABLE posts ADD COLUMN latest_notice TEXT;
    CREATE INDEX comments_activity ON comments(guild_id, thread_id, activity_at DESC);
    """,
    USER_TIMEZONES_SCHEMA,
    """
    CREATE TABLE local_review_requests(message_id INTEGER PRIMARY KEY);
    """,
    """
    CREATE TABLE plugin_command_guilds(guild_id INTEGER PRIMARY KEY);
    """,
)


def migrate(path: str) -> None:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE IF NOT EXISTS schema_version(version INTEGER NOT NULL)")
        row = db.execute("SELECT version FROM schema_version").fetchone()
        version = row[0] if row else 0
        if version > len(MIGRATIONS):
            raise RuntimeError("Database schema is newer than this Lifeguard version")
        for index, sql in enumerate(MIGRATIONS[version:], version + 1):
            db.executescript(
                "BEGIN IMMEDIATE;\n" + sql + "\nDELETE FROM schema_version;\n"
                f"INSERT INTO schema_version VALUES ({index});\nCOMMIT;"
            )


class SqliteEnablementStore:
    def __init__(self, path: str):
        if path != ":memory:":
            migrate(path)
        self.db = sqlite3.connect(path)
        if path == ":memory:":
            for sql in MIGRATIONS:
                self.db.executescript(sql)

    def guilds_for(self, name: str) -> set[int]:
        return {
            row[0]
            for row in self.db.execute("SELECT guild_id FROM enablement WHERE name=?", (name,))
        }

    def add(self, name: str, guild_id: int) -> None:
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO enablement VALUES (?,?)", (name, guild_id))

    def remove(self, name: str, guild_id: int) -> None:
        with self.db:
            self.db.execute("DELETE FROM enablement WHERE name=? AND guild_id=?", (name, guild_id))

    def command_guilds(self) -> set[int]:
        return {row[0] for row in self.db.execute("SELECT guild_id FROM plugin_command_guilds")}

    def track_command_guild(self, guild_id: int, tracked: bool) -> None:
        with self.db:
            if tracked:
                self.db.execute(
                    "INSERT OR IGNORE INTO plugin_command_guilds VALUES (?)", (guild_id,)
                )
            else:
                self.db.execute("DELETE FROM plugin_command_guilds WHERE guild_id=?", (guild_id,))

    def close(self) -> None:
        self.db.close()
