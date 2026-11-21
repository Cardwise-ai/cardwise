"""Per-user limits on sending messages (spec 7.2): 20 an hour and one stream at a time.

Both are stored in `app.usage_counters` so every serverless instance sees the same numbers.

- Messages: a fixed one-hour window per user, counted with one atomic upsert that refuses to
  go past the limit, so concurrent requests cannot overshoot.
- Streams: a lease row per open stream. Acquiring takes a transaction-scoped advisory lock on
  the user (safe with the transaction pooler), drops leases older than `lease_s` and inserts a
  new one only if fewer than the limit remain. A function killed mid-stream therefore blocks
  its user for at most `lease_s`, not forever.
"""

import math
import zlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final, Protocol
from uuid import UUID

import asyncpg

MESSAGES_KIND: Final = "messages_hour"
STREAM_KIND: Final = "stream"
WINDOW: Final = timedelta(hours=1)
STREAM_BUSY_RETRY_S: Final = 5


class RateLimitedError(Exception):
    def __init__(self, retry_after_s: int) -> None:
        super().__init__(f"rate limited, retry after {retry_after_s}s")
        self.retry_after_s = max(1, retry_after_s)


@dataclass(frozen=True, slots=True)
class StreamLease:
    subject: str
    started_at: datetime


class RateLimiter(Protocol):
    async def acquire_stream(self, user_id: UUID) -> StreamLease:
        """Raises RateLimitedError when the user already has the maximum open streams."""
        ...

    async def release_stream(self, lease: StreamLease) -> None: ...

    async def count_message(self, user_id: UUID) -> None:
        """Counts one message. Raises RateLimitedError, without counting, when over the limit."""
        ...


def subject(user_id: UUID) -> str:
    return f"user:{user_id}"


def _window(now: datetime) -> datetime:
    return now.replace(minute=0, second=0, microsecond=0)


def _seconds_until_next_window(now: datetime) -> int:
    return math.ceil((_window(now) + WINDOW - now).total_seconds())


def _lock_key(subject: str) -> int:
    """A stable 32-bit key for pg_advisory_xact_lock, namespaced away from ingest's lock."""
    return zlib.crc32(f"cardwise-ratelimit:{subject}".encode()) - 2**31


class PgRateLimiter:
    def __init__(
        self,
        conn: asyncpg.Connection,
        *,
        messages_per_hour: int,
        concurrent_streams: int,
        lease_s: int,
    ) -> None:
        self._conn = conn
        self._messages_per_hour = messages_per_hour
        self._concurrent_streams = concurrent_streams
        self._lease_s = lease_s

    async def count_message(self, user_id: UUID) -> None:
        counted = await self._conn.fetchval(
            "insert into app.usage_counters as u (subject, kind, window_start, count)"
            " values ($1, $2, date_trunc('hour', now()), 1)"
            " on conflict (subject, kind, window_start) do update set count = u.count + 1"
            " where u.count < $3"
            " returning u.count",
            subject(user_id),
            MESSAGES_KIND,
            self._messages_per_hour,
        )
        if counted is None:
            now: datetime = await self._conn.fetchval("select now()")
            raise RateLimitedError(_seconds_until_next_window(now))

    async def acquire_stream(self, user_id: UUID) -> StreamLease:
        key = subject(user_id)
        async with self._conn.transaction():
            await self._conn.execute("select pg_advisory_xact_lock($1)", _lock_key(key))
            await self._conn.execute(
                "delete from app.usage_counters"
                " where subject = $1 and kind = $2"
                " and window_start < clock_timestamp() - $3::int * interval '1 second'",
                key,
                STREAM_KIND,
                self._lease_s,
            )
            started_at: datetime | None = await self._conn.fetchval(
                "insert into app.usage_counters (subject, kind, window_start, count)"
                " select $1, $2, clock_timestamp(), 1"
                " where (select count(*) from app.usage_counters"
                "        where subject = $1 and kind = $2) < $3"
                " returning window_start",
                key,
                STREAM_KIND,
                self._concurrent_streams,
            )
        if started_at is None:
            raise RateLimitedError(STREAM_BUSY_RETRY_S)
        return StreamLease(key, started_at)

    async def release_stream(self, lease: StreamLease) -> None:
        await self._conn.execute(
            "delete from app.usage_counters where subject = $1 and kind = $2 and window_start = $3",
            lease.subject,
            STREAM_KIND,
            lease.started_at,
        )


class InMemoryRateLimiter:
    """Same rules in process memory, for tests and local runs without a database."""

    def __init__(
        self,
        *,
        messages_per_hour: int,
        concurrent_streams: int,
        lease_s: int,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._messages_per_hour = messages_per_hour
        self._concurrent_streams = concurrent_streams
        self._lease = timedelta(seconds=lease_s)
        self._clock = clock
        self._counts: dict[tuple[str, datetime], int] = {}
        self.leases: dict[str, list[datetime]] = {}

    async def count_message(self, user_id: UUID) -> None:
        now = self._clock()
        key = (subject(user_id), _window(now))
        if self._counts.get(key, 0) >= self._messages_per_hour:
            raise RateLimitedError(_seconds_until_next_window(now))
        self._counts[key] = self._counts.get(key, 0) + 1

    async def acquire_stream(self, user_id: UUID) -> StreamLease:
        key, now = subject(user_id), self._clock()
        live = [t for t in self.leases.get(key, []) if t >= now - self._lease]
        self.leases[key] = live
        if len(live) >= self._concurrent_streams:
            raise RateLimitedError(STREAM_BUSY_RETRY_S)
        # Leases are keyed by start time; nudge past an equal one so each stays distinct.
        while now in live:
            now += timedelta(microseconds=1)
        live.append(now)
        return StreamLease(key, now)

    async def release_stream(self, lease: StreamLease) -> None:
        held = self.leases.get(lease.subject, [])
        if lease.started_at in held:
            held.remove(lease.started_at)
