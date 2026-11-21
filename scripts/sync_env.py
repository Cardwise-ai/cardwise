"""Sync Cardwise environment variables from Supabase into GitHub and Vercel.

Reads what it can from the Supabase Management API (pooler host, region,
publishable key), asks for what Supabase never shows again (database password,
S3 access keys), checks every value against the live service, then writes:

- GitHub environment secrets (dev, prod) used by the ingest workflow;
- cardwise-web variables in Vercel (Production -> prod, Preview and
  Development -> dev).

Re-running is safe: every write overwrites. Nothing is written to disk.

    uv run python scripts/sync_env.py                 # both projects
    uv run python scripts/sync_env.py --env dev --dry-run

Supabase token: SUPABASE_ACCESS_TOKEN, else the token `supabase login` stored.
The token must reach both projects. Unattended runs take secrets from
CARDWISE_SYNC_<DEV|PROD>_DB_PASSWORD, ..._S3_ACCESS_KEY_ID and
..._S3_SECRET_ACCESS_KEY. An empty answer skips that group of secrets.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import getpass
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

import asyncpg
import boto3
import httpx
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
REPO = "Cardwise-ai/cardwise"
VERCEL_PROJECT = "cardwise-web"
VERCEL_CLI = "vercel@66"
BUCKET = "raw-snapshots"
API = "https://api.supabase.com"
SESSION_POOLER_PORT = 5432


class SyncError(Exception):
    pass


class Project(BaseModel):
    ref: str
    name: str
    region: str
    status: str


class Pooler(BaseModel):
    database_type: str
    db_host: str
    db_user: str
    db_name: str


class ApiKey(BaseModel):
    name: str
    type: str | None = None
    api_key: str | None = None


@dataclass(frozen=True)
class Target:
    name: str
    ref: str
    vercel_environments: str


@dataclass
class Plan:
    github: dict[str, str] = field(default_factory=dict)
    vercel: dict[str, str] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def _windows_credential(target: str) -> str | None:
    import ctypes
    from ctypes import wintypes

    class Credential(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    advapi32 = ctypes.WinDLL("advapi32")  # type: ignore[attr-defined,unused-ignore]
    pointer = ctypes.POINTER(Credential)()
    if not advapi32.CredReadW(target, 1, 0, ctypes.byref(pointer)):
        return None
    try:
        cred = pointer.contents
        return bytes(cred.CredentialBlob[: cred.CredentialBlobSize]).decode()
    finally:
        advapi32.CredFree(pointer)


def supabase_token() -> str:
    if token := os.environ.get("SUPABASE_ACCESS_TOKEN"):
        return token
    stored: str | None = None
    if sys.platform == "win32":
        stored = _windows_credential("Supabase CLI:supabase")
    file = Path.home() / ".supabase" / "access-token"
    if stored is None and file.exists():
        stored = file.read_text(encoding="utf-8").strip()
    if stored and stored.startswith("go-keyring-base64:"):
        stored = base64.b64decode(stored.split(":", 1)[1]).decode()
    if stored:
        return stored
    raise SyncError(
        "No Supabase token. Run `pnpm exec supabase login`, or set SUPABASE_ACCESS_TOKEN "
        "to a token from https://supabase.com/dashboard/account/tokens."
    )


class Supabase:
    def __init__(self, token: str) -> None:
        self._client = httpx.Client(
            base_url=API, headers={"Authorization": f"Bearer {token}"}, timeout=30
        )

    def _get(self, path: str) -> object:
        response = self._client.get(path)
        if response.status_code == 401:
            raise SyncError("Supabase rejected the token; run `pnpm exec supabase login` again.")
        if response.status_code == 403:
            raise SyncError(
                f"the Supabase token can't read {path}. A `supabase login` token only covers the "
                "organizations you granted. Create a token at "
                "https://supabase.com/dashboard/account/tokens and set SUPABASE_ACCESS_TOKEN."
            )
        if response.status_code == 404:
            raise SyncError(f"Supabase has no {path}; check the project ref.")
        response.raise_for_status()
        return response.json()

    def project(self, ref: str) -> Project:
        return Project.model_validate(self._get(f"/v1/projects/{ref}"))

    def primary_pooler(self, ref: str) -> Pooler:
        raw = self._get(f"/v1/projects/{ref}/config/database/pooler")
        poolers = [Pooler.model_validate(item) for item in raw]  # type: ignore[attr-defined]
        for pooler in poolers:
            if pooler.database_type == "PRIMARY":
                return pooler
        raise SyncError(f"{ref} has no primary pooler")

    def api_keys(self, ref: str) -> list[ApiKey]:
        raw = self._get(f"/v1/projects/{ref}/api-keys")
        return [ApiKey.model_validate(item) for item in raw]  # type: ignore[attr-defined]


def key_of_type(keys: list[ApiKey], kind: str) -> str:
    for key in keys:
        if key.type == kind and key.api_key:
            return key.api_key
    raise SyncError(f"no {kind} API key; create one under Project Settings -> API Keys")


def session_pooler_url(pooler: Pooler, password: str) -> str:
    return (
        f"postgresql://{pooler.db_user}:{quote(password, safe='')}"
        f"@{pooler.db_host}:{SESSION_POOLER_PORT}/{pooler.db_name}"
    )


async def _check_database(url: str) -> str:
    connection = await asyncpg.connect(url, timeout=20)
    try:
        version = await connection.fetchval("show server_version")
        snapshots = await connection.fetchval("select to_regclass('corpus.snapshots') is not null")
    finally:
        await connection.close()
    return f"Postgres {version}, corpus schema {'present' if snapshots else 'MISSING'}"


def check_database(url: str) -> str:
    try:
        return asyncio.run(_check_database(url))
    except asyncpg.InvalidPasswordError as error:
        raise SyncError("wrong database password") from error
    except (OSError, asyncpg.PostgresError, TimeoutError) as error:
        raise SyncError(f"can't reach the session pooler: {error}") from error


def check_s3(endpoint: str, region: str, key_id: str, secret: str) -> None:
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
        aws_access_key_id=key_id,
        aws_secret_access_key=secret,
        config=Config(
            s3={"addressing_style": "path"},
            connect_timeout=10,
            read_timeout=20,
            retries={"max_attempts": 1},
        ),
    )
    try:
        client.list_objects_v2(Bucket=BUCKET, MaxKeys=1)
    except (BotoCoreError, ClientError) as error:
        raise SyncError(f"S3 keys don't reach bucket {BUCKET}: {error}") from error


def secret_input(prompt: str, env_var: str, *, hidden: bool) -> str:
    if value := os.environ.get(env_var):
        return value
    if not sys.stdin.isatty():
        return ""
    return (getpass.getpass(prompt) if hidden else input(prompt)).strip()


def plan_target(supabase: Supabase, target: Target) -> Plan:
    plan = Plan()
    project = supabase.project(target.ref)
    if project.status != "ACTIVE_HEALTHY":
        raise SyncError(f"{project.name} is {project.status}; restore it in the dashboard first")
    print(f"\n{project.name} ({target.ref}, {project.region})")

    plan.vercel["NEXT_PUBLIC_SUPABASE_URL"] = f"https://{target.ref}.supabase.co"
    plan.vercel["NEXT_PUBLIC_SUPABASE_ANON_KEY"] = key_of_type(
        supabase.api_keys(target.ref), "publishable"
    )

    prefix = f"CARDWISE_SYNC_{target.name.upper()}_"
    print(f"  Database password: Project Settings -> Database ({project.name})")
    password = secret_input(
        "  database password (empty to skip): ", f"{prefix}DB_PASSWORD", hidden=True
    )
    if password:
        url = session_pooler_url(supabase.primary_pooler(target.ref), password)
        print(f"  database: {check_database(url)}")
        plan.github["CARDWISE_DATABASE_URL"] = url
    else:
        plan.skipped.append(f"{target.name}: CARDWISE_DATABASE_URL")

    endpoint = f"https://{target.ref}.storage.supabase.co/storage/v1/s3"
    print(f"  S3 keys: Project Settings -> Storage -> S3 Access Keys ({project.name})")
    key_id = secret_input(
        "  S3 access key id (empty to skip): ", f"{prefix}S3_ACCESS_KEY_ID", hidden=False
    )
    secret = (
        secret_input("  S3 secret access key: ", f"{prefix}S3_SECRET_ACCESS_KEY", hidden=True)
        if key_id
        else ""
    )
    if key_id and secret:
        check_s3(endpoint, project.region, key_id, secret)
        print("  S3 keys: reach the bucket")
        plan.github.update(
            {
                "CARDWISE_STORAGE_S3_ENDPOINT": endpoint,
                "CARDWISE_STORAGE_S3_REGION": project.region,
                "CARDWISE_STORAGE_S3_ACCESS_KEY_ID": key_id,
                "CARDWISE_STORAGE_S3_SECRET_ACCESS_KEY": secret,
            }
        )
    else:
        plan.skipped.append(
            f"{target.name}: CARDWISE_STORAGE_S3_* (ingest won't archive raw files)"
        )
    return plan


def mask(value: str) -> str:
    return value if value.startswith("https://") else f"{value[:4]}... ({len(value)} chars)"


def tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise SyncError(f"{name} isn't on PATH")
    return path


def run(args: list[str], value: str) -> None:
    result = subprocess.run(args, input=value, capture_output=True, text=True, check=False)  # noqa: S603
    if result.returncode != 0:
        raise SyncError(
            f"{Path(args[0]).stem} {args[1]} {args[2]} failed: {result.stderr.strip()[-300:]}"
        )


def apply(target: Target, plan: Plan, *, vercel_scope: str, github: bool, vercel: bool) -> None:
    if github:
        gh = tool("gh")
        for name, value in plan.github.items():
            run([gh, "secret", "set", name, "--env", target.name, "--repo", REPO], value)
            print(f"  set GitHub {target.name} secret {name}")
    if vercel:
        npx = tool("npx")
        for name, value in plan.vercel.items():
            run(
                [
                    npx, "--yes", VERCEL_CLI, "env", "add", name,
                    "--environment", target.vercel_environments,
                    "--project", VERCEL_PROJECT, "--scope", vercel_scope,
                    "--no-sensitive", "--force", "--yes",
                ],
                value,
            )  # fmt: skip
            print(f"  set Vercel {name} ({target.vercel_environments})")


def main(argv: list[str] | None = None) -> int:
    hosted = read_env_file(ROOT / ".env.hosted")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--env", choices=["dev", "prod"], action="append", help="default: both")
    parser.add_argument("--dev-ref", default=hosted.get("SUPABASE_DEV_REF"))
    parser.add_argument("--prod-ref", default=hosted.get("SUPABASE_PROD_REF"))
    parser.add_argument("--vercel-scope", default=hosted.get("VERCEL_SCOPE"))
    parser.add_argument("--skip-github", action="store_true")
    parser.add_argument("--skip-vercel", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="check and print, change nothing")
    args = parser.parse_args(argv)

    refs = {"dev": args.dev_ref, "prod": args.prod_ref}
    vercel_environments = {"dev": "preview,development", "prod": "production"}
    try:
        missing = [f"--{name}-ref" for name in args.env or refs if not refs[name]]
        if missing or (not args.skip_vercel and not args.vercel_scope):
            raise SyncError(f"missing {', '.join(missing) or '--vercel-scope'} (or .env.hosted)")
        supabase = Supabase(supabase_token())
    except SyncError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    failed: list[str] = []
    for name in args.env or ["dev", "prod"]:
        target = Target(name, refs[name], vercel_environments[name])
        try:
            plan = plan_target(supabase, target)
            verb = "would set" if args.dry_run else "syncing"
            for kind, values in (("GitHub", plan.github), ("Vercel", plan.vercel)):
                for key, value in values.items():
                    print(f"  {verb} {kind} {key} = {mask(value)}")
            for skipped in plan.skipped:
                print(f"  skipped {skipped}")
            if not args.dry_run:
                apply(
                    target,
                    plan,
                    vercel_scope=args.vercel_scope,
                    github=not args.skip_github,
                    vercel=not args.skip_vercel,
                )
        except (SyncError, httpx.HTTPError) as error:
            print(f"\n{name}: error: {error}", file=sys.stderr)
            failed.append(name)
    if failed:
        print(f"\nnot synced: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
