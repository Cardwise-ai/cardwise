"""Checks the migrated schema in the local Supabase database.

Run `pnpm exec supabase db start` first. Each test runs in a transaction that is
rolled back, so tests leave no rows behind.
"""

import os
from collections.abc import AsyncIterator
from uuid import uuid4

import asyncpg
import pytest

pytestmark = pytest.mark.db

DSN = os.environ.get(
    "CARDWISE_TEST_DB_URL", "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
)
SCHEMAS = ("corpus", "app")
FAKE_SHA256 = "0" * 64


@pytest.fixture
async def conn() -> AsyncIterator[asyncpg.Connection]:
    connection = await asyncpg.connect(DSN)
    tx = connection.transaction()
    await tx.start()
    try:
        yield connection
    finally:
        await tx.rollback()
        await connection.close()


async def _new_snapshot(conn: asyncpg.Connection, status: str = "loading") -> int:
    snapshot_id: int = await conn.fetchval(
        "insert into corpus.snapshots"
        " (status, source_updated_at, storage_path, activated_at, content_sha256, source_files)"
        " values ($1, now(), 'raw-snapshots/test', case when $1 = 'active' then now() end,"
        " $2, '{}')"
        " returning id",
        status,
        FAKE_SHA256,
    )
    return snapshot_id


async def _new_user(conn: asyncpg.Connection) -> str:
    user_id = str(uuid4())
    await conn.execute(
        "insert into auth.users (id, email) values ($1, $2)", user_id, f"{user_id}@test.invalid"
    )
    return user_id


async def test_every_table_has_rls_enabled(conn: asyncpg.Connection) -> None:
    rows = await conn.fetch(
        "select n.nspname, c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace"
        " where n.nspname = any($1::text[]) and c.relkind = 'r' and not c.relrowsecurity",
        list(SCHEMAS),
    )
    assert [f"{r['nspname']}.{r['relname']}" for r in rows] == []


@pytest.mark.parametrize("role", ["anon", "authenticated"])
async def test_api_roles_cannot_reach_private_schemas(conn: asyncpg.Connection, role: str) -> None:
    for schema in SCHEMAS:
        assert not await conn.fetchval("select has_schema_privilege($1, $2, 'USAGE')", role, schema)
    granted = await conn.fetchval(
        "select count(*) from information_schema.role_table_grants"
        " where grantee = $1 and table_schema = any($2::text[])",
        role,
        list(SCHEMAS),
    )
    assert granted == 0


async def test_only_one_snapshot_can_be_active(conn: asyncpg.Connection) -> None:
    await _new_snapshot(conn, "active")
    with pytest.raises(asyncpg.UniqueViolationError):
        await _new_snapshot(conn, "active")


async def test_active_snapshot_requires_activation_time(conn: asyncpg.Connection) -> None:
    with pytest.raises(asyncpg.CheckViolationError):
        await conn.execute(
            "insert into corpus.snapshots"
            " (status, source_updated_at, storage_path, content_sha256, source_files)"
            " values ('active', now(), 'raw-snapshots/test', $1, '{}')",
            FAKE_SHA256,
        )


async def test_snapshot_rejects_malformed_content_hash(conn: asyncpg.Connection) -> None:
    with pytest.raises(asyncpg.CheckViolationError):
        await conn.execute(
            "insert into corpus.snapshots (source_updated_at, content_sha256, source_files)"
            " values (now(), 'not-a-hash', '{}')"
        )


async def test_mana_value_fits_gleemax(conn: asyncpg.Connection) -> None:
    snapshot_id = await _new_snapshot(conn)
    await conn.execute(
        "insert into corpus.cards (snapshot_id, oracle_id, name, layout, is_game_card, mana_value,"
        " type_line, legalities, scryfall_uri, search_text, payload)"
        " values ($1, $2, 'Gleemax', 'normal', true, 1000000, 'Legendary Artifact', '{}',"
        " 'https://scryfall.com/card/x', 'Gleemax', '{}')",
        snapshot_id,
        uuid4(),
    )


async def test_card_search_vector_includes_text(conn: asyncpg.Connection) -> None:
    snapshot_id = await _new_snapshot(conn)
    oracle_id = uuid4()
    await conn.execute(
        "insert into corpus.cards (snapshot_id, oracle_id, name, layout, is_game_card, mana_value,"
        " type_line, legalities, scryfall_uri, search_text, payload, color_identity)"
        " values ($1, $2, 'Test Elk', 'normal', true, 3, 'Creature - Elk', '{}',"
        " 'https://scryfall.com/card/x',"
        " 'Test Elk. Whenever another creature enters, draw a card.',"
        " '{}', array['G'])",
        snapshot_id,
        oracle_id,
    )
    found = await conn.fetchval(
        "select oracle_id from corpus.cards"
        " where search_tsv @@ plainto_tsquery('english', 'draws cards')"
    )
    assert found == oracle_id


async def test_card_rejects_unknown_color(conn: asyncpg.Connection) -> None:
    snapshot_id = await _new_snapshot(conn)
    with pytest.raises(asyncpg.CheckViolationError):
        await conn.execute(
            "insert into corpus.cards (snapshot_id, oracle_id, name, layout, is_game_card,"
            " mana_value,"
            " type_line, legalities, scryfall_uri, search_text, payload, color_identity)"
            " values ($1, $2, 'Bad', 'normal', true, 1, 'Instant', '{}', 'https://scryfall.com/card/x',"
            " 'Bad', '{}', array['P'])",
            snapshot_id,
            uuid4(),
        )


async def test_deleting_snapshot_removes_its_rows(conn: asyncpg.Connection) -> None:
    snapshot_id = await _new_snapshot(conn)
    tag_id = uuid4()
    await conn.execute(
        "insert into corpus.tags (snapshot_id, tag_id, slug, label)"
        " values ($1, $2, 'ramp', 'Ramp')",
        snapshot_id,
        tag_id,
    )
    await conn.execute("delete from corpus.snapshots where id = $1", snapshot_id)
    assert (
        await conn.fetchval("select count(*) from corpus.tags where snapshot_id = $1", snapshot_id)
        == 0
    )


async def test_chat_title_length_is_bounded(conn: asyncpg.Connection) -> None:
    user_id = await _new_user(conn)
    with pytest.raises(asyncpg.CheckViolationError):
        await conn.execute(
            "insert into app.chats (user_id, title) values ($1, $2)", user_id, "x" * 121
        )


async def test_user_messages_cannot_carry_model_fields(conn: asyncpg.Connection) -> None:
    user_id = await _new_user(conn)
    chat_id = await conn.fetchval(
        "insert into app.chats (user_id, title) values ($1, 'Ramp') returning id", user_id
    )
    with pytest.raises(asyncpg.CheckViolationError):
        await conn.execute(
            "insert into app.messages (chat_id, role, content, model)"
            " values ($1, 'user', 'hi', 'gemini')",
            chat_id,
        )


async def test_deleting_user_removes_their_chats(conn: asyncpg.Connection) -> None:
    user_id = await _new_user(conn)
    chat_id = await conn.fetchval(
        "insert into app.chats (user_id, title) values ($1, 'Ramp') returning id", user_id
    )
    message_id = await conn.fetchval(
        "insert into app.messages (chat_id, role, content)"
        " values ($1, 'user', 'cards like x') returning id",
        chat_id,
    )
    await conn.execute(
        "insert into app.message_cards (message_id, position, oracle_id, name)"
        " values ($1, 0, $2, 'Elk')",
        message_id,
        uuid4(),
    )
    await conn.execute("delete from auth.users where id = $1", user_id)
    assert await conn.fetchval("select count(*) from app.messages where chat_id = $1", chat_id) == 0
    assert (
        await conn.fetchval(
            "select count(*) from app.message_cards where message_id = $1", message_id
        )
        == 0
    )
