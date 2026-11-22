"""Download the bulk files and record what was fetched.

A manifest (`manifest.json`) sits next to the files with each file's SHA-256, so a run can be
replayed from a directory and still prove it read the same bytes.
"""

import hashlib
import logging
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated

import httpx
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, HttpUrl

from cardwise_ingest.scryfall import BULK_TYPES, BulkIndex, BulkType

log = logging.getLogger(__name__)

MANIFEST_NAME = "manifest.json"
CHUNK_SIZE = 1 << 20
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class DownloadError(RuntimeError):
    pass


def _plain_filename(name: str) -> str:
    if not name or "/" in name or "\\" in name or name.startswith("."):
        raise ValueError(f"not a plain file name: {name!r}")
    return name


class SourceFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: BulkType
    uri: HttpUrl
    updated_at: datetime
    filename: Annotated[str, AfterValidator(_plain_filename)]
    size: Annotated[int, Field(ge=0)]
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    files: dict[BulkType, SourceFile]

    @property
    def content_sha256(self) -> str:
        """Hash of the per-file hashes. Equal values mean byte-identical inputs."""
        lines = "".join(f"{t}:{self.files[t].sha256}\n" for t in sorted(self.files))
        return hashlib.sha256(lines.encode()).hexdigest()

    @property
    def source_updated_at(self) -> datetime:
        return max(f.updated_at for f in self.files.values())

    def path(self, directory: Path, bulk_type: BulkType) -> Path:
        return directory / self.files[bulk_type].filename

    def write(self, directory: Path) -> None:
        (directory / MANIFEST_NAME).write_text(self.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def read(cls, directory: Path) -> "Manifest":
        """Load a manifest and check that every file still matches its recorded hash."""
        manifest = cls.model_validate_json((directory / MANIFEST_NAME).read_text("utf-8"))
        missing = [t for t in BULK_TYPES if t not in manifest.files]
        if missing:
            raise DownloadError(f"manifest is missing {', '.join(missing)}")
        for f in manifest.files.values():
            size, digest = _hash_file(directory / f.filename)
            if (size, digest) != (f.size, f.sha256):
                raise DownloadError(f"{f.filename} does not match its manifest entry")
        return manifest


def _hash_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK_SIZE):
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


def _with_retries[T](action: str, attempt: Callable[[], T], retries: int, backoff: float) -> T:
    for n in range(retries + 1):
        try:
            return attempt()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in RETRYABLE_STATUS or n == retries:
                raise DownloadError(f"{action}: HTTP {exc.response.status_code}") from exc
            error: Exception = exc
        except httpx.TransportError as exc:
            if n == retries:
                raise DownloadError(f"{action}: {exc}") from exc
            error = exc
        delay = backoff * 2**n
        log.warning("%s failed (%s); retrying in %.0fs", action, error, delay)
        time.sleep(delay)
    raise AssertionError("unreachable")  # pragma: no cover


def fetch_index(
    client: httpx.Client, url: str, *, retries: int = 3, backoff: float = 2.0
) -> BulkIndex:
    def attempt() -> BulkIndex:
        response = client.get(url)
        response.raise_for_status()
        return BulkIndex.model_validate_json(response.content)

    return _with_retries("bulk index", attempt, retries, backoff)


def download_all(
    client: httpx.Client,
    index_url: str,
    directory: Path,
    *,
    retries: int = 3,
    backoff: float = 2.0,
) -> Manifest:
    """Download every bulk file we need into `directory` and write its manifest."""
    directory.mkdir(parents=True, exist_ok=True)
    index = fetch_index(client, index_url, retries=retries, backoff=backoff)
    by_type = {item.type: item for item in index.data}
    files: dict[BulkType, SourceFile] = {}
    for bulk_type in BULK_TYPES:
        item = by_type.get(bulk_type)
        if item is None or item.jsonl_download_uri is None:
            raise DownloadError(f"bulk index has no {bulk_type} file")
        uri = item.jsonl_download_uri
        filename = _plain_filename(Path(uri.path or "").name)
        target = directory / filename

        def attempt(uri: HttpUrl = uri, target: Path = target) -> tuple[int, str]:
            return _stream_to(client, str(uri), target)

        size, digest = _with_retries(bulk_type, attempt, retries, backoff)
        if item.compressed_size is not None and item.compressed_size != size:
            log.warning(
                "%s: index says %d bytes, downloaded %d", bulk_type, item.compressed_size, size
            )
        log.info("downloaded %s (%d bytes, sha256 %s)", filename, size, digest)
        files[bulk_type] = SourceFile(
            type=bulk_type,
            uri=uri,
            updated_at=item.updated_at,
            filename=filename,
            size=size,
            sha256=digest,
        )
    manifest = Manifest(files=files)
    manifest.write(directory)
    return manifest


def _stream_to(client: httpx.Client, url: str, target: Path) -> tuple[int, str]:
    partial = target.with_name(target.name + ".part")
    digest = hashlib.sha256()
    size = 0
    # Hash the exact bytes Scryfall publishes; no transfer encoding on top of the gzip.
    with client.stream("GET", url, headers={"Accept-Encoding": "identity"}) as response:
        response.raise_for_status()
        with partial.open("wb") as fh:
            for chunk in response.iter_raw(CHUNK_SIZE):
                fh.write(chunk)
                digest.update(chunk)
                size += len(chunk)
    partial.replace(target)
    return size, digest.hexdigest()


def scryfall_client(
    user_agent: str, *, transport: httpx.BaseTransport | None = None
) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": user_agent, "Accept": "application/json"},
        timeout=httpx.Timeout(30.0, read=120.0),
        follow_redirects=False,
        transport=transport,
    )
