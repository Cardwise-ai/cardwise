"""Archive raw bulk files to the private `raw-snapshots` bucket (Supabase Storage, S3 API).

Archives are for replay and debugging, not backup, so a failure here is logged and the run
goes on without one.
"""

import gzip
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from cardwise_ingest.download import MANIFEST_NAME, Manifest
from cardwise_ingest.settings import IngestSettings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client
    from mypy_boto3_s3.type_defs import ObjectIdentifierTypeDef

log = logging.getLogger(__name__)

MAX_OBJECT_BYTES = 50 * 1024 * 1024
"""Supabase Free plan upload limit per object."""

CONTENT_TYPE = "application/gzip"
"""The bucket accepts gzip only (supabase/config.toml), so the manifest is gzipped too."""


class ObjectStore(Protocol):
    def upload(self, key: str, path: Path, content_type: str) -> None: ...

    def prefixes(self) -> list[str]:
        """Top-level `<date>/` prefixes in the bucket."""
        ...

    def delete_prefix(self, prefix: str) -> None: ...


class S3Store:
    def __init__(self, client: "S3Client", bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    @classmethod
    def from_settings(cls, settings: IngestSettings) -> "S3Store":
        import boto3
        from botocore.config import Config

        key_id = settings.storage_s3_access_key_id
        secret = settings.storage_s3_secret_access_key
        if settings.storage_s3_endpoint is None or key_id is None or secret is None:
            raise ValueError("S3 storage is not configured")
        client = boto3.client(
            "s3",
            endpoint_url=str(settings.storage_s3_endpoint),
            region_name=settings.storage_s3_region,
            aws_access_key_id=key_id.get_secret_value(),
            aws_secret_access_key=secret.get_secret_value(),
            config=Config(s3={"addressing_style": "path"}, retries={"mode": "standard"}),
        )
        return cls(client, settings.storage_bucket)

    def upload(self, key: str, path: Path, content_type: str) -> None:
        self._client.upload_file(
            str(path), self._bucket, key, ExtraArgs={"ContentType": content_type}
        )

    def prefixes(self) -> list[str]:
        found: list[str] = []
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Delimiter="/"):
            found.extend(p["Prefix"] for p in page.get("CommonPrefixes", []) if "Prefix" in p)
        return found

    def delete_prefix(self, prefix: str) -> None:
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            keys: list[ObjectIdentifierTypeDef] = [
                {"Key": o["Key"]} for o in page.get("Contents", []) if "Key" in o
            ]
            if keys:
                self._client.delete_objects(Bucket=self._bucket, Delete={"Objects": keys})


def archive(store: ObjectStore, bucket: str, manifest: Manifest, directory: Path) -> str | None:
    """Upload the files and manifest under `<date>/`. Returns the storage path, or None."""
    prefix = f"{manifest.source_updated_at.date().isoformat()}/"
    try:
        for f in manifest.files.values():
            if f.size > MAX_OBJECT_BYTES:
                log.warning(
                    "%s is %d bytes, over the upload limit; not archived", f.filename, f.size
                )
                return None
        manifest_gz = directory / f"{MANIFEST_NAME}.gz"
        manifest_gz.write_bytes(gzip.compress((directory / MANIFEST_NAME).read_bytes(), mtime=0))
        for f in manifest.files.values():
            store.upload(prefix + f.filename, directory / f.filename, CONTENT_TYPE)
        store.upload(prefix + manifest_gz.name, manifest_gz, CONTENT_TYPE)
    except Exception:
        log.exception("archiving raw files failed; continuing without an archive")
        return None
    log.info("archived raw files to %s/%s", bucket, prefix)
    return f"{bucket}/{prefix}"


def prune(store: ObjectStore, keep: int) -> None:
    """Delete all but the newest `keep` dated prefixes."""
    try:
        dated = sorted(p for p in store.prefixes() if len(p) == 11 and p[4] == "-")
        for prefix in dated[:-keep]:
            store.delete_prefix(prefix)
            log.info("deleted archived snapshot %s", prefix)
    except Exception:
        log.exception("pruning archived snapshots failed")
