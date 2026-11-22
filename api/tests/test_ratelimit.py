"""Rate limits. The in-memory tests run everywhere; the `db` ones need the local database."""

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import asyncpg
import pytest

from cardwise_api.ratelimit import (
    STREAM_KIND,
    InMemoryRateLimiter,
    PgRateLimiter,
    RateLimitedError,
    subject,
)

DSN = os.environ.get(
    "CARDWISE_TEST_DB_URL", "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
)


async def test_message_window_resets_on_the_hour() -> None:
    now = [datetime(2026, 11, 21, 10, 59, 30, tzinfo=UTC)]
    limiter = InMemoryRateLimiter(
        messages_per_hour=2, concurrent_streams=1, lease_s=60, clock=lambda: now[0]
    )
    user = uuid4()
    await limiter.count_message(user)
    await limiter.count_message(user)
    with pytest.raises(RateLimitedError) as limited:
        await limiter.count_message(user)
    assert limited.value.retry_after_s == 30
    now[0] += timedelta(seconds=30)
    await limiter.count_message(user)


async def test_stale_stream_leases_expire() -> None:
    now = [datetime(2026, 11, 21, 10, tzinfo=UTC)]
    limiter = InMemoryRateLimiter(
        messages_per_hour=20, concurrent_streams=1, lease_s=60, clock=lambda: now[0]
    )
    user = uuid4()
    await limiter.acquire_stream(user)  # never released: the function died
    with pytest.raises(RateLimitedError):
        await limiter.acquire_stream(user)
    now[0] += timedelta(seconds=61)
    await limiter.acquire_stream(user)


# Postgres ---------------------------------------------------------------------------------


@pytest.fixture
async def conn() -> AsyncIterator[asyncpg.Connection]:
    connection = await asyncpg.connect(DSN, statement_cache_size=0)
    tx = connection.transaction()
    await tx.start()
    try:
        yield connection
    finally:
        await tx.rollback()
        await connection.close()


def pg_limiter(conn: asyncpg.Connection, *, messages: int = 3, lease_s: int = 60) -> PgRateLimiter:
    return PgRateLimiter(conn, messages_per_hour=messages, concurrent_streams=1, lease_s=lease_s)


@pytest.mark.db
async def test_pg_counts_up_to_the_limit_then_refuses(conn: asyncpg.Connection) -> None:
    limiter, user = pg_limiter(conn), uuid4()
    for _ in range(3):
        await limiter.count_message(user)
    with pytest.raises(RateLimitedError) as limited:
        await limiter.count_message(user)
    assert 1 <= limited.value.retry_after_s <= 3600
    count = await conn.fetchval(
        "select count from app.usage_counters where subject = $1 and kind = 'messages_hour'",
        subject(user),
    )
    assert count == 3


@pytest.mark.db
async def test_pg_concurrent_counts_never_overshoot() -> None:
    user = uuid4()
    connections = [await asyncpg.connect(DSN, statement_cache_size=0) for _ in range(6)]
    try:
        results = await asyncio.gather(
            *(pg_limiter(c).count_message(user) for c in connections), return_exceptions=True
        )
        assert sum(isinstance(r, RateLimitedError) for r in results) == 3
    finally:
        await connections[0].execute(
            "delete from app.usage_counters where subject = $1", subject(user)
        )
        for c in connections:
            await c.close()


@pytest.mark.db
async def test_pg_one_stream_per_user(conn: asyncpg.Connection) -> None:
    limiter, user = pg_limiter(conn), uuid4()
    lease = await limiter.acquire_stream(user)
    with pytest.raises(RateLimitedError):
        await limiter.acquire_stream(user)
    await limiter.acquire_stream(uuid4())  # other users are unaffected
    await limiter.release_stream(lease)
    await limiter.acquire_stream(user)


@pytest.mark.db
async def test_pg_stale_lease_expires(conn: asyncpg.Connection) -> None:
    user: UUID = uuid4()
    await conn.execute(
        "insert into app.usage_counters (subject, kind, window_start, count)"
        " values ($1, $2, clock_timestamp() - interval '2 minutes', 1)",
        subject(user),
        STREAM_KIND,
    )
    await pg_limiter(conn, lease_s=60).acquire_stream(user)
