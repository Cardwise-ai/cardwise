from collections.abc import Callable
from pathlib import Path

from cardwise_ingest.archive import archive, prune
from cardwise_ingest.download import MANIFEST_NAME, Manifest


class FakeStore:
    def __init__(self, existing: list[str] | None = None, *, broken: bool = False) -> None:
        self.objects: dict[str, bytes] = dict.fromkeys(existing or [], b"")
        self.broken = broken

    def upload(self, key: str, path: Path) -> None:
        if self.broken:
            raise OSError("storage is down")
        self.objects[key] = path.read_bytes()

    def prefixes(self) -> list[str]:
        return sorted({key.split("/")[0] + "/" for key in self.objects})

    def delete_prefix(self, prefix: str) -> None:
        self.objects = {k: v for k, v in self.objects.items() if not k.startswith(prefix)}


def test_archive_uploads_files_and_manifest_under_date(
    tmp_path: Path, make_bulk_dir: Callable[..., Manifest]
) -> None:
    manifest = make_bulk_dir()
    store = FakeStore()
    assert archive(store, "raw-snapshots", manifest, tmp_path) == "raw-snapshots/2026-11-21/"
    expected = {f"2026-11-21/{f.filename}" for f in manifest.files.values()}
    assert set(store.objects) == expected | {f"2026-11-21/{MANIFEST_NAME}"}


def test_archive_failure_is_not_fatal(
    tmp_path: Path, make_bulk_dir: Callable[..., Manifest]
) -> None:
    manifest = make_bulk_dir()
    assert archive(FakeStore(broken=True), "raw-snapshots", manifest, tmp_path) is None


def test_prune_keeps_newest_dated_prefixes() -> None:
    store = FakeStore(
        [f"2026-11-{day:02d}/x.gz" for day in (1, 8, 15, 22, 29)] + ["notes/readme.txt"]
    )
    prune(store, keep=4)
    assert store.prefixes() == [
        "2026-11-08/",
        "2026-11-15/",
        "2026-11-22/",
        "2026-11-29/",
        "notes/",
    ]
