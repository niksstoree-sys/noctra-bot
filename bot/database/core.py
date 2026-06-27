"""
Thin async SQLite wrapper around aiosqlite.

Kept deliberately simple: one shared connection, WAL mode for better
concurrent read/write behaviour, and a handful of helper methods
(`execute`, `fetchone`, `fetchall`, `executescript`) that every query module
in `bot/database/queries/` builds on. This is what makes a future migration
to Postgres/MySQL straightforward -- only this file and the queries would
need to change, not the cogs.
"""

from __future__ import annotations

import os
from pathlib import Path

import aiosqlite

from bot.core.logger import logger


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        Path(os.path.dirname(self.path) or ".").mkdir(parents=True, exist_ok=True)
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA foreign_keys = ON;")
        await self.conn.execute("PRAGMA journal_mode = WAL;")
        await self.conn.commit()
        logger.info("Database connected at %s", self.path)

    async def close(self) -> None:
        if self.conn:
            await self.conn.close()
            logger.info("Database connection closed.")

    async def init_schema(self) -> None:
        schema_path = Path(__file__).parent / "schema.sql"
        sql = schema_path.read_text(encoding="utf-8")
        assert self.conn is not None
        await self.conn.executescript(sql)
        await self.conn.commit()
        logger.info("Database schema ensured.")

    async def execute(self, query: str, params: tuple = ()) -> int | None:
        assert self.conn is not None
        cursor = await self.conn.execute(query, params)
        await self.conn.commit()
        return cursor.lastrowid

    async def executemany(self, query: str, seq_of_params) -> None:
        assert self.conn is not None
        await self.conn.executemany(query, seq_of_params)
        await self.conn.commit()

    async def fetchone(self, query: str, params: tuple = ()) -> aiosqlite.Row | None:
        assert self.conn is not None
        cursor = await self.conn.execute(query, params)
        row = await cursor.fetchone()
        await cursor.close()
        return row

    async def fetchall(self, query: str, params: tuple = ()) -> list[aiosqlite.Row]:
        assert self.conn is not None
        cursor = await self.conn.execute(query, params)
        rows = await cursor.fetchall()
        await cursor.close()
        return list(rows)
