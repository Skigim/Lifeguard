"""Serialized async access; every mutation commits before returning."""

import asyncio
import time

import aiosqlite

from lifeguard.core.db import MIGRATIONS, migrate


class Store:
    def __init__(self, db):
        self.db = db
        self.lock = asyncio.Lock()

    @classmethod
    async def open(cls, path):
        if path != ":memory:":
            migrate(path)
        db = await aiosqlite.connect(path)
        db.row_factory = aiosqlite.Row
        if path == ":memory:":
            for sql in MIGRATIONS:
                await db.executescript(sql)
        await db.execute("PRAGMA busy_timeout=5000")
        return cls(db)

    async def close(self):
        await self.db.close()

    async def all(self, sql, args=()):
        async with self.lock, self.db.execute(sql, args) as cursor:
            return [dict(row) for row in await cursor.fetchall()]

    async def one(self, sql, args=()):
        rows = await self.all(sql, args)
        return rows[0] if rows else None

    async def execute(self, sql, args=()):
        async with self.lock, self.db.execute(sql, args) as cursor:
            await self.db.commit()
            return cursor.rowcount

    async def put(self, table, **values):
        # Table and column names are internal constants, never command input.
        keys = ",".join(values)
        marks = ",".join("?" for _ in values)
        await self.execute(
            f"INSERT OR REPLACE INTO {table} ({keys}) VALUES ({marks})", tuple(values.values())
        )

    async def links(self, repo=None):
        if repo:
            return await self.all("SELECT * FROM repo_links WHERE repo=?", (repo.lower(),))
        return await self.all("SELECT * FROM repo_links")

    async def post(self, guild, repo, number):
        return await self.one(
            "SELECT * FROM posts WHERE guild_id=? AND repo=? AND number=?", (guild, repo, number)
        )

    async def comment(self, guild, repo, kind, comment_id):
        return await self.one(
            "SELECT * FROM comments WHERE guild_id=? AND repo=? AND gh_kind=? AND gh_comment_id=?",
            (guild, repo, kind, comment_id),
        )

    async def processed(self, delivery):
        return await self.one("SELECT * FROM deliveries WHERE delivery_id=?", (delivery,))

    async def finish(self, delivery, received):
        # Cursor is receipt time, not completion time: recovery must include queued events.
        async with self.lock:
            await self.db.execute(
                "INSERT OR IGNORE INTO deliveries VALUES (?,?,?)", (delivery, received, time.time())
            )
            await self.db.execute(
                "INSERT INTO bridge_state VALUES ('last_event',?) ON CONFLICT(key) DO UPDATE "
                "SET value=MAX(CAST(value AS REAL),CAST(excluded.value AS REAL))",
                (str(received),),
            )
            await self.db.execute(
                "DELETE FROM deliveries WHERE processed_at<?", (time.time() - 7 * 86400,)
            )
            await self.db.commit()

    async def consume_state(self, state):
        async with self.lock:
            async with self.db.execute(
                "DELETE FROM oauth_states WHERE state=? RETURNING *", (state,)
            ) as cur:
                row = await cur.fetchone()
            await self.db.execute(
                "DELETE FROM oauth_states WHERE created_at<?", (time.time() - 600,)
            )
            await self.db.commit()
            return dict(row) if row and row["created_at"] > time.time() - 600 else None
