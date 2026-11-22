"""End-to-end ingest into the local Supabase database. Run `pnpm exec supabase db start` first.

The pipeline manages its own transactions, so these tests commit and clean up afterwards.
"""

import json
import os
from collections.abc import AsyncIterator, Callable
from decimal import Decimal
from pathlib import Path

import asyncpg
import pytest
from pydantic import SecretStr

from cardwise_ingest import load
from cardwise_ingest.download import Manifest
from cardwise_ingest.pipeline import IngestError, Options, run
from cardwise_ingest.scryfall import BulkType
from cardwise_ingest.settings import IngestSettings
from cardwise_ingest.transform import Corpus

pytestmark = pytest.mark.db

DSN = os.environ.get(
    "CARDWISE_TEST_DB_URL", "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
)


@pytest.fixture
async def conn() -> AsyncIterator[asyncpg.Connection]:
    connection = await asyncpg.connect(DSN)
    before: int = await connection.fetchval("select coalesce(max(id), 0) from corpus.snapshots")
    if await connection.fetchval("select count(*) from corpus.snapshots where status = 'active'"):
        await connection.close()
        pytest.skip("database already has an active snapshot")
    try:
        yield connection
    finally:
        await connection.execute("delete from corpus.snapshots where id > $1", before)
        await connection.close()


@pytest.fixture
def db_settings(settings: IngestSettings) -> IngestSettings:
    return settings.model_copy(update={"database_url": SecretStr(DSN)})


async def statuses(conn: asyncpg.Connection) -> list[tuple[int, str]]:
    rows = await conn.fetch("select id, status from corpus.snapshots order by id")
    return [(r["id"], r["status"]) for r in rows]


async def test_load_activate_noop_and_prune(
    conn: asyncpg.Connection,
    db_settings: IngestSettings,
    tmp_path: Path,
    make_bulk_dir: Callable[..., Manifest],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = make_bulk_dir()
    options = Options(tmp_path, from_dir=True, archive=False)

    first = await run(db_settings, options)
    assert first.result == "loaded"
    assert first.report is not None
    sid = first.snapshot_id
    for table, expected in [
        ("cards", first.report.counts["cards"]),
        ("card_faces", first.report.counts["faces"]),
        ("rulings", first.report.counts["rulings"]),
        ("tags", first.report.counts["tags"]),
        ("tag_parents", first.report.counts["tag_edges"]),
        ("card_tags", first.report.counts["card_tags"]),
    ]:
        count = await conn.fetchval(
            f"select count(*) from corpus.{table} where snapshot_id = $1",  # noqa: S608
            sid,
        )
        assert count == expected, table

    snapshot = await conn.fetchrow("select * from corpus.snapshots where id = $1", sid)
    assert snapshot is not None
    assert snapshot["status"] == "active"
    assert snapshot["content_sha256"] == manifest.content_sha256
    assert set(json.loads(snapshot["source_files"])) == {"oracle_cards", "rulings", "oracle_tags"}

    gleemax = await conn.fetchrow(
        "select mana_value, payload from corpus.cards where snapshot_id = $1 and name = 'Gleemax'",
        sid,
    )
    assert gleemax is not None
    assert gleemax["mana_value"] == Decimal(1_000_000)
    assert "prices" not in json.loads(gleemax["payload"])
    defense = await conn.fetchval(
        "select defense from corpus.card_faces f join corpus.cards c using (snapshot_id, oracle_id)"
        " where c.snapshot_id = $1 and f.name = 'Invasion of Zendikar'",
        sid,
    )
    assert defense == "3"
    found = await conn.fetchval(
        "select name from corpus.cards where snapshot_id = $1"
        " and search_tsv @@ plainto_tsquery('english', 'prevented stomp')",
        sid,
    )
    assert found == "Bonecrusher Giant // Stomp"

    second = await run(db_settings, options)
    assert (second.result, second.snapshot_id) == ("unchanged", sid)

    during_load: list[list[str]] = []
    load_rows = load.load_rows

    async def spy(c: asyncpg.Connection, snapshot_id: int, corpus: Corpus) -> dict[str, int]:
        during_load.append([s for _, s in await statuses(conn)])
        return await load_rows(c, snapshot_id, corpus)

    monkeypatch.setattr(load, "load_rows", spy)
    forced = [await run(db_settings, Options(tmp_path, from_dir=True, archive=False, force=True))]
    forced.append(
        await run(db_settings, Options(tmp_path, from_dir=True, archive=False, force=True))
    )
    ids = [o.snapshot_id for o in forced]
    assert await statuses(conn) == [(ids[0], "retired"), (ids[1], "active")]
    # The retired snapshot is gone before the next one loads (Free plan disk limit).
    assert during_load == [["active", "loading"], ["active", "loading"]]


async def test_failed_validation_keeps_live_snapshot(
    conn: asyncpg.Connection,
    db_settings: IngestSettings,
    tmp_path: Path,
    make_bulk_dir: Callable[..., Manifest],
    bulk_lines: dict[BulkType, list[str]],
) -> None:
    make_bulk_dir()
    live = await run(db_settings, Options(tmp_path, from_dir=True, archive=False))

    broken = [*bulk_lines["oracle_cards"], bulk_lines["oracle_cards"][0]]
    make_bulk_dir({"oracle_cards": broken})
    with pytest.raises(IngestError, match="duplicate oracle_id"):
        await run(db_settings, Options(tmp_path, from_dir=True, archive=False))

    rows = await statuses(conn)
    assert rows[0] == (live.snapshot_id, "active")
    assert rows[1][1] == "failed"
    quarantined = await conn.fetchval(
        "select count(*) from corpus.quarantine where snapshot_id = $1", rows[1][0]
    )
    assert quarantined == 1
    assert (
        await conn.fetchval("select count(*) from corpus.cards where snapshot_id = $1", rows[1][0])
        == 0
    )
