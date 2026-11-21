"""Fixtures are real Scryfall lines from the 2026-11-21 bulk files, picked for tricky layouts."""

import gzip
import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import HttpUrl

from cardwise_ingest.download import Manifest, SourceFile
from cardwise_ingest.scryfall import BulkType
from cardwise_ingest.settings import IngestSettings

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE_FILES: dict[BulkType, str] = {
    "oracle_cards": "cards.jsonl",
    "rulings": "rulings.jsonl",
    "oracle_tags": "oracle_tags.jsonl",
}


def fixture_lines(bulk_type: BulkType) -> list[str]:
    return (FIXTURES / FIXTURE_FILES[bulk_type]).read_text("utf-8").splitlines(keepends=True)


@pytest.fixture
def bulk_lines() -> dict[BulkType, list[str]]:
    return {t: fixture_lines(t) for t in FIXTURE_FILES}


@pytest.fixture
def settings() -> IngestSettings:
    return IngestSettings(min_cards=1, min_tags=1, min_rulings=1, max_quarantine_ratio=0.5)


@pytest.fixture
def make_bulk_dir(tmp_path: Path) -> Callable[..., Manifest]:
    """Write gzipped bulk files and a manifest to tmp_path; lines default to the fixtures."""

    def make(overrides: dict[BulkType, list[str]] | None = None) -> Manifest:
        files: dict[BulkType, SourceFile] = {}
        for bulk_type in FIXTURE_FILES:
            lines = (overrides or {}).get(bulk_type) or fixture_lines(bulk_type)
            name = f"{bulk_type.replace('_', '-')}-20261121100000.jsonl.gz"
            data = gzip.compress("".join(lines).encode(), mtime=0)
            (tmp_path / name).write_bytes(data)
            files[bulk_type] = SourceFile(
                type=bulk_type,
                uri=HttpUrl(f"https://data.scryfall.io/{bulk_type}/{name}"),
                updated_at=datetime(2026, 11, 21, 10, tzinfo=UTC),
                filename=name,
                size=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
            )
        manifest = Manifest(files=files)
        manifest.write(tmp_path)
        return manifest

    return make
