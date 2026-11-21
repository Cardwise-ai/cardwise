"""One ingest run: fetch, parse, validate, archive, load, activate."""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import asyncpg

from cardwise_ingest import archive, load
from cardwise_ingest.download import Manifest, download_all, scryfall_client
from cardwise_ingest.settings import IngestSettings
from cardwise_ingest.transform import Corpus, build_corpus
from cardwise_ingest.validate import Report, validate

log = logging.getLogger(__name__)


class IngestError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Options:
    work_dir: Path
    """Where bulk files are downloaded to, or read from with `from_dir`."""
    from_dir: bool = False
    dry_run: bool = False
    force: bool = False
    allow_count_drift: bool = False
    archive: bool = True


@dataclass(frozen=True, slots=True)
class Outcome:
    result: Literal["loaded", "unchanged", "dry_run"]
    content_sha256: str
    report: Report | None = None
    snapshot_id: int | None = None


def fetch(settings: IngestSettings, options: Options) -> Manifest:
    if options.from_dir:
        return Manifest.read(options.work_dir)
    with scryfall_client(settings.user_agent) as client:
        return download_all(client, str(settings.bulk_index_url), options.work_dir)


def parse(manifest: Manifest, directory: Path) -> Corpus:
    corpus = build_corpus(
        manifest.path(directory, "oracle_cards"),
        manifest.path(directory, "rulings"),
        manifest.path(directory, "oracle_tags"),
    )
    log.info(
        "parsed %d cards, %d rulings, %d tags, %d taggings; %d quarantined",
        len(corpus.cards),
        len(corpus.rulings),
        len(corpus.tags),
        len(corpus.card_tags),
        len(corpus.quarantine),
    )
    return corpus


async def run(settings: IngestSettings, options: Options) -> Outcome:
    manifest = fetch(settings, options)
    log.info("content sha256 %s", manifest.content_sha256)

    if options.dry_run:
        report = validate(
            parse(manifest, options.work_dir),
            settings,
            previous_card_count=None,
            allow_count_drift=options.allow_count_drift,
        )
        if not report.ok:
            raise IngestError("; ".join(report.errors))
        return Outcome("dry_run", manifest.content_sha256, report)

    if settings.database_url is None:
        raise IngestError("CARDWISE_DATABASE_URL is not set (use --dry-run to skip the load)")
    conn = await asyncpg.connect(settings.database_url.get_secret_value())
    try:
        await conn.execute("set statement_timeout = '15min'")
        async with load.ingest_lock(conn):
            return await _load(conn, settings, options, manifest)
    finally:
        await conn.close()


async def _load(
    conn: asyncpg.Connection, settings: IngestSettings, options: Options, manifest: Manifest
) -> Outcome:
    await load.fail_stale_runs(conn)
    active = await load.active_snapshot(conn)
    if active and active.content_sha256 == manifest.content_sha256 and not options.force:
        log.info("snapshot %d already has these files; nothing to do", active.id)
        return Outcome("unchanged", manifest.content_sha256, snapshot_id=active.id)

    corpus = parse(manifest, options.work_dir)
    report = validate(
        corpus,
        settings,
        previous_card_count=active.card_count if active else None,
        allow_count_drift=options.allow_count_drift,
    )

    store = (
        archive.S3Store.from_settings(settings)
        if options.archive and settings.s3_configured
        else None
    )
    storage_path = (
        archive.archive(store, settings.storage_bucket, manifest, options.work_dir)
        if store
        else None
    )
    if store is None:
        log.info("raw files not archived (storage not configured or --no-archive)")

    snapshot_id = await load.create_snapshot(conn, manifest, storage_path, corpus.quarantine)
    if not report.ok:
        reason = "validation failed: " + "; ".join(report.errors)
        await load.mark_failed(conn, snapshot_id, reason)
        raise IngestError(f"snapshot {snapshot_id}: {reason}")
    try:
        await load.load_rows(conn, snapshot_id, corpus)
        await load.activate(conn, snapshot_id, load.notes_for(report))
    except Exception as exc:
        await load.mark_failed(conn, snapshot_id, f"load failed: {exc}")
        raise
    log.info("snapshot %d is active", snapshot_id)
    await load.prune(conn)
    if store:
        archive.prune(store, settings.raw_snapshots_kept)
    return Outcome("loaded", manifest.content_sha256, report, snapshot_id)
