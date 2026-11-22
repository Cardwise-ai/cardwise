"""Postgres access over the Supabase transaction pooler.

Plain asyncpg rather than SQLAlchemy: the API runs a handful of hand-written statements and
maps rows to Pydantic models itself, so an ORM would add cold-start time and bundle size
without removing code (docs/adr/0007). The rules for serverless + transaction pooling:

- no client-side pool: each request opens one connection and closes it when the response is
  done. The pooler (port 6543) is the pool, so a frozen Vercel instance holds no backends.
- no prepared statement cache (`statement_cache_size=0`): with transaction pooling, a
  statement prepared on one server connection is gone on the next transaction. asyncpg then
  uses unnamed statements only, which the pooler supports.
- the API connects as a privileged role that bypasses RLS, so every query on user data
  filters by the authenticated user ID (see chats/repository.py).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Final

import asyncpg

CONNECT_TIMEOUT_S: Final = 10.0
COMMAND_TIMEOUT_S: Final = 15.0


class DatabaseNotConfiguredError(RuntimeError):
    pass


class Database:
    def __init__(self, dsn: str | None) -> None:
        self._dsn = dsn

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[asyncpg.Connection]:
        if self._dsn is None:
            raise DatabaseNotConfiguredError("CARDWISE_DATABASE_URL is not set")
        conn: asyncpg.Connection = await asyncpg.connect(
            self._dsn,
            statement_cache_size=0,
            timeout=CONNECT_TIMEOUT_S,
            command_timeout=COMMAND_TIMEOUT_S,
        )
        try:
            yield conn
        finally:
            await conn.close(timeout=5)
