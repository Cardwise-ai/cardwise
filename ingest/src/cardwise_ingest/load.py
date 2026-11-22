"""Load a validated corpus into Postgres as a new snapshot and activate it (B5).

Transactions:
1. Insert the snapshot row (`loading`) and its quarantine rows; committed so a failed run
   still leaves a record of what went wrong.
2. COPY every table, check the row counts, mark `validated`.
3. Retire the active snapshot and activate the new one.
Then prune: keep the active snapshot and the one before it.
"""

import json
import logging
from collections.abc import AsyncIterator, Iterable, Sequence
from contextlib import asynccontextmanager
from dataclasses import astuple, dataclass
from typing import Any

import asyncpg

from cardwise_ingest.download import Manifest
from cardwise_ingest.transform import Corpus, QuarantineRow
from cardwise_ingest.validate import Report

log = logging.getLogger(__name__)

LOCK_KEY = 0x63617264_696E6773  # "cardings": one ingest at a time per database.
QUARANTINE_ROW_LIMIT = 1000
"""Quarantine rows stored per run. Counts in the snapshot notes cover the rest."""


class LoadError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ActiveSnapshot:
    id: int
    content_sha256: str
    card_count: int | None


@asynccontextmanager
async def ingest_lock(conn: asyncpg.Connection) -> AsyncIterator[None]:
    if not await conn.fetchval("select pg_try_advisory_lock($1)", LOCK_KEY):
        raise LoadError("another ingest run holds the lock")
    try:
        yield
    finally:
        await conn.execute("select pg_advisory_unlock($1)", LOCK_KEY)


async def fail_stale_runs(conn: asyncpg.Connection) -> None:
    """Runs that died mid-load leave `loading`/`validated` rows; only the lock holder may do so."""
    status = await conn.execute(
        "update corpus.snapshots set status = 'failed',"
        " notes = coalesce(notes || E'\\n', '') || 'interrupted: marked failed by a later run'"
        " where status in ('loading', 'validated')"
    )
    if status != "UPDATE 0":
        log.warning("marked interrupted snapshots failed (%s)", status)


async def active_snapshot(conn: asyncpg.Connection) -> ActiveSnapshot | None:
    row = await conn.fetchrow(
        "select id, content_sha256, card_count from corpus.snapshots where status = 'active'"
    )
    if row is None:
        return None
    return ActiveSnapshot(row["id"], row["content_sha256"], row["card_count"])


def _source_files(manifest: Manifest) -> str:
    return json.dumps({t: f.model_dump(mode="json") for t, f in manifest.files.items()})


async def create_snapshot(
    conn: asyncpg.Connection,
    manifest: Manifest,
    storage_path: str | None,
    quarantine: Sequence[QuarantineRow],
) -> int:
    async with conn.transaction():
        snapshot_id: int = await conn.fetchval(
            "insert into corpus.snapshots"
            " (source_updated_at, storage_path, content_sha256, source_files)"
            " values ($1, $2, $3, $4::jsonb) returning id",
            manifest.source_updated_at,
            storage_path,
            manifest.content_sha256,
            _source_files(manifest),
        )
        await conn.copy_records_to_table(
            "quarantine",
            schema_name="corpus",
            columns=["snapshot_id", "source", "record_key", "reason", "payload"],
            records=[
                (snapshot_id, q.source, q.record_key, q.reason, json.dumps(q.payload))
                for q in quarantine[:QUARANTINE_ROW_LIMIT]
            ],
        )
    return snapshot_id


async def mark_failed(conn: asyncpg.Connection, snapshot_id: int, reason: str) -> None:
    await conn.execute(
        "update corpus.snapshots set status = 'failed', notes = $2"
        " where id = $1 and status in ('loading', 'validated')",
        snapshot_id,
        reason[:4000],
    )


def _json(value: Any) -> str | None:
    return None if value is None else json.dumps(value, ensure_ascii=False)


TABLES: dict[str, list[str]] = {
    "cards": [
        "oracle_id", "name", "layout", "is_game_card", "mana_cost", "mana_value", "type_line",
        "oracle_text", "colors", "color_identity", "keywords", "legalities", "image_uris",
        "scryfall_uri", "edhrec_rank", "released_at", "search_text", "payload",
    ],
    "card_faces": [
        "oracle_id", "face_index", "name", "mana_cost", "type_line", "oracle_text",
        "image_uris", "power", "toughness", "loyalty", "defense",
    ],
    "rulings": ["oracle_id", "source", "published_at", "comment"],
    "tags": ["tag_id", "slug", "label", "description", "aliases"],
    "tag_parents": ["tag_id", "parent_id"],
    "card_tags": ["tag_id", "oracle_id", "weight", "annotation"],
}  # fmt: skip
"""Columns in dataclass field order, without snapshot_id."""

JSON_COLUMNS = frozenset({"legalities", "image_uris", "payload"})


def _records(snapshot_id: int, table: str, rows: Iterable[Any]) -> list[tuple[Any, ...]]:
    columns = TABLES[table]
    json_at = [i for i, c in enumerate(columns) if c in JSON_COLUMNS]
    out = []
    for row in rows:
        values = list(astuple(row))
        for i in json_at:
            values[i] = _json(values[i])
        out.append((snapshot_id, *values))
    return out


async def load_rows(conn: asyncpg.Connection, snapshot_id: int, corpus: Corpus) -> dict[str, int]:
    """COPY every table in one transaction and mark the snapshot validated."""
    plan: list[tuple[str, Sequence[Any]]] = [
        ("cards", corpus.cards),
        ("card_faces", corpus.faces),
        ("rulings", corpus.rulings),
        ("tags", corpus.tags),
        ("tag_parents", corpus.tag_edges),
        ("card_tags", corpus.card_tags),
    ]
    counts: dict[str, int] = {}
    async with conn.transaction():
        for table, rows in plan:
            await conn.copy_records_to_table(
                table,
                schema_name="corpus",
                columns=["snapshot_id", *TABLES[table]],
                records=_records(snapshot_id, table, rows),
            )
            # Table names come from the fixed plan above, never from input.
            loaded: int = await conn.fetchval(
                f"select count(*) from corpus.{table} where snapshot_id = $1",  # noqa: S608
                snapshot_id,
            )
            if loaded != len(rows):
                raise LoadError(f"{table}: loaded {loaded} rows, expected {len(rows)}")
            counts[table] = loaded
            log.info("loaded %d %s", loaded, table)
        await conn.execute(
            "update corpus.snapshots set status = 'validated',"
            " card_count = $2, tag_count = $3, ruling_count = $4"
            " where id = $1 and status = 'loading'",
            snapshot_id,
            counts["cards"],
            counts["tags"],
            counts["rulings"],
        )
    return counts


async def activate(conn: asyncpg.Connection, snapshot_id: int, notes: str | None) -> None:
    async with conn.transaction():
        await conn.execute("update corpus.snapshots set status = 'retired' where status = 'active'")
        status = await conn.execute(
            "update corpus.snapshots set status = 'active', activated_at = now(), notes = $2"
            " where id = $1 and status = 'validated'",
            snapshot_id,
            notes,
        )
        if status != "UPDATE 1":
            raise LoadError(f"snapshot {snapshot_id} was not in state validated")


CORPUS_TABLES = ("cards", "card_faces", "rulings", "tags", "tag_parents", "card_tags", "quarantine")


async def make_room(conn: asyncpg.Connection) -> int:
    """Delete every snapshot but the active one, then vacuum so the next load reuses the space.

    One snapshot is ~180 MB and the Free plan allows 500 MB, so a load must never run next to
    two older snapshots. The active one stays live until the new one replaces it.
    """
    status = await conn.execute("delete from corpus.snapshots where status <> 'active'")
    deleted = int(status.split()[-1])
    if deleted:
        log.info("deleted %d inactive snapshots before loading", deleted)
        tables = ", ".join(f"corpus.{t}" for t in CORPUS_TABLES)
        await conn.execute(f"vacuum (analyze) {tables}")
    return deleted


async def prune(conn: asyncpg.Connection) -> int:
    """Keep the active snapshot and the most recent retired one; deletes cascade."""
    status = await conn.execute(
        "delete from corpus.snapshots s"
        " where s.status in ('retired', 'failed')"
        " and s.id < (select id from corpus.snapshots where status = 'active')"
        " and s.id is distinct from ("
        "   select max(id) from corpus.snapshots where status = 'retired')"
    )
    deleted = int(status.split()[-1])
    if deleted:
        log.info("pruned %d old snapshots", deleted)
    return deleted


def notes_for(report: Report) -> str | None:
    bad = {k: v for k, v in report.quarantined.items() if v}
    if not bad:
        return None
    return "quarantined: " + ", ".join(f"{k} {v}" for k, v in sorted(bad.items()))
