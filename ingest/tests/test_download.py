import gzip
import hashlib
import json
from pathlib import Path

import httpx
import pytest

from cardwise_ingest.download import DownloadError, Manifest, download_all, scryfall_client

INDEX_URL = "https://api.scryfall.com/bulk-data"
BODIES = {
    "oracle_cards": gzip.compress(b'{"a": 1}\n', mtime=0),
    "rulings": gzip.compress(b'{"b": 2}\n', mtime=0),
    "oracle_tags": gzip.compress(b'{"c": 3}\n', mtime=0),
}


def _index(host: str = "data.scryfall.io") -> bytes:
    items = [
        {
            "type": t,
            "updated_at": "2026-11-21T10:00:00+00:00",
            "jsonl_download_uri": f"https://{host}/{t}/{t}-20261121.jsonl.gz",
            "compressed_size": len(body),
        }
        for t, body in BODIES.items()
    ]
    items.append({"type": "all_cards", "updated_at": "2026-11-21T10:00:00+00:00"})
    return json.dumps({"object": "list", "data": items}).encode()


def _client(handler: httpx.MockTransport) -> httpx.Client:
    return scryfall_client("Cardwise/test", transport=handler)


def _serve(
    failures: dict[str, int] | None = None, host: str = "data.scryfall.io"
) -> httpx.MockTransport:
    remaining = dict(failures or {})
    seen_headers: list[httpx.Headers] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.append(request.headers)
        if str(request.url) == INDEX_URL:
            return httpx.Response(200, content=_index(host))
        bulk_type = request.url.path.split("/")[1]
        if remaining.get(bulk_type, 0) > 0:
            remaining[bulk_type] -= 1
            return httpx.Response(503)
        return httpx.Response(200, stream=httpx.ByteStream(BODIES[bulk_type]))

    transport = httpx.MockTransport(handler)
    transport.seen_headers = seen_headers  # type: ignore[attr-defined]
    return transport


def test_download_records_hashes_and_writes_manifest(tmp_path: Path) -> None:
    transport = _serve()
    with _client(transport) as client:
        manifest = download_all(client, INDEX_URL, tmp_path, backoff=0)
    for bulk_type, body in BODIES.items():
        f = manifest.files[bulk_type]  # type: ignore[index]
        assert f.sha256 == hashlib.sha256(body).hexdigest()
        assert (tmp_path / f.filename).read_bytes() == body
    assert Manifest.read(tmp_path) == manifest
    assert all(h["user-agent"] == "Cardwise/test" for h in transport.seen_headers)  # type: ignore[attr-defined]
    assert not list(tmp_path.glob("*.part"))


def test_content_hash_changes_with_any_file(tmp_path: Path) -> None:
    with _client(_serve()) as client:
        manifest = download_all(client, INDEX_URL, tmp_path, backoff=0)
    changed = manifest.model_copy(
        update={
            "files": {
                **manifest.files,
                "rulings": manifest.files["rulings"].model_copy(update={"sha256": "0" * 64}),
            }
        }
    )
    assert changed.content_sha256 != manifest.content_sha256
    assert len(manifest.content_sha256) == 64


def test_transient_errors_are_retried(tmp_path: Path) -> None:
    with _client(_serve({"rulings": 2})) as client:
        manifest = download_all(client, INDEX_URL, tmp_path, backoff=0)
    assert manifest.files["rulings"].size == len(BODIES["rulings"])


def test_persistent_errors_fail(tmp_path: Path) -> None:
    with _client(_serve({"rulings": 9})) as client, pytest.raises(DownloadError, match="503"):
        download_all(client, INDEX_URL, tmp_path, retries=2, backoff=0)


def test_files_must_come_from_scryfall(tmp_path: Path) -> None:
    with _client(_serve(host="evil.example")) as client, pytest.raises(Exception, match="scryfall"):
        download_all(client, INDEX_URL, tmp_path, backoff=0)


def test_manifest_read_detects_changed_files(tmp_path: Path) -> None:
    with _client(_serve()) as client:
        manifest = download_all(client, INDEX_URL, tmp_path, backoff=0)
    (tmp_path / manifest.files["oracle_cards"].filename).write_bytes(b"tampered")
    with pytest.raises(DownloadError, match="does not match"):
        Manifest.read(tmp_path)
