# 0007: asyncpg without an ORM in the API

Status: accepted
Date: 2026-11-21

## Context
The spec (§7) planned SQLAlchemy 2 async on top of asyncpg, with `NullPool` and the prepared-statement cache off. The API runs as a Vercel Python function and reaches Postgres through the Supabase transaction pooler (Supavisor, port 6543). In transaction mode each transaction may land on a different server connection, so named prepared statements break, and a client-side pool in a frozen function instance only holds pooler slots.

What the API actually stores is small: chats, messages, message cards and usage counters, read and written by about a dozen hand-written statements that map rows straight to the Pydantic contract models. Ingest already uses plain asyncpg.

## Decision
- The API uses asyncpg directly (`cardwise_api.db`). No SQLAlchemy, no ORM models.
- One connection per request, opened by a FastAPI dependency and closed after the response, streams included. No client-side pool; the pooler is the pool.
- `statement_cache_size=0` on every connection, so asyncpg only uses unnamed statements, which the transaction pooler supports. No session state (`SET`, advisory session locks, `LISTEN`) is used; locks are transaction-scoped (`pg_advisory_xact_lock`).
- The API connects as a privileged role that bypasses RLS. Every statement on user data filters by the authenticated user ID; a chat owned by someone else is indistinguishable from a missing one (404). RLS stays on as a second layer for any client that talks to Postgres directly.
- SQL lives in repository classes (`chats/repository.py`, `ratelimit.py`) behind protocols with in-memory twins for unit tests. `@pytest.mark.db` tests run the real SQL against the local database in CI.

## Consequences
- Smaller bundle and faster cold start than SQLAlchemy, one database driver across the repo, and the SQL is visible where it runs.
- No migrations or schema reflection from Python: the schema is owned by `supabase/migrations`, and the db tests catch drift.
- Queries are composed by hand. If the API grows many dynamic filters or the number of tables climbs, revisit SQLAlchemy Core (not the ORM) for query building.
- Opening a connection per request costs a pooler round trip (~a few ms in the same region). If that shows up in latency, keep one connection per function instance instead of a pool.
