"""Command line: `python -m cardwise_ingest {download,run}`."""

import argparse
import asyncio
import logging
import os
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from cardwise_ingest.download import DownloadError, download_all, scryfall_client
from cardwise_ingest.load import LoadError
from cardwise_ingest.pipeline import IngestError, Options, Outcome, run
from cardwise_ingest.settings import IngestSettings

log = logging.getLogger("cardwise_ingest")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cardwise_ingest", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    dl = sub.add_parser("download", help="download the bulk files and a manifest into DIR")
    dl.add_argument("dir", type=Path)

    r = sub.add_parser("run", help="download (or read), validate, load and activate a snapshot")
    r.add_argument("--from-dir", type=Path, help="use files from `download DIR` instead")
    r.add_argument("--work-dir", type=Path, help="keep downloaded files here (default: temp)")
    r.add_argument("--dry-run", action="store_true", help="parse and validate only; no database")
    r.add_argument("--force", action="store_true", help="load even if the files are unchanged")
    r.add_argument(
        "--allow-count-drift", action="store_true", help="skip the card count change check"
    )
    r.add_argument("--no-archive", action="store_true", help="do not upload raw files")
    return parser


def _summary(outcome: Outcome) -> str:
    lines = [
        f"Ingest result: **{outcome.result}**",
        "",
        f"- content sha256 `{outcome.content_sha256}`",
    ]
    if outcome.snapshot_id is not None:
        lines.append(f"- snapshot {outcome.snapshot_id}")
    if outcome.report:
        lines += [f"- {name}: {count}" for name, count in outcome.report.counts.items()]
        lines += [f"- quarantined {k}: {v}" for k, v in outcome.report.quarantined.items()]
    return "\n".join(lines) + "\n"


def _write_step_summary(text: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with Path(path).open("a", encoding="utf-8") as fh:
            fh.write(text)


def _run(args: argparse.Namespace, settings: IngestSettings) -> None:
    work_dir = args.from_dir or args.work_dir or Path(tempfile.mkdtemp(prefix="cardwise-ingest-"))
    options = Options(
        work_dir,
        from_dir=args.from_dir is not None,
        dry_run=args.dry_run,
        force=args.force,
        allow_count_drift=args.allow_count_drift,
        archive=not args.no_archive,
    )
    outcome = asyncio.run(run(settings, options))
    summary = _summary(outcome)
    log.info("%s", summary)
    _write_step_summary(summary)


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    args = _parser().parse_args(argv)
    try:
        settings = IngestSettings()
        if args.command == "download":
            with scryfall_client(settings.user_agent) as client:
                download_all(client, str(settings.bulk_index_url), args.dir)
        else:
            _run(args, settings)
    except (IngestError, DownloadError, LoadError, ValidationError) as exc:
        log.error("ingest failed: %s", exc)
        _write_step_summary(f"Ingest result: **failed**\n\n```\n{exc}\n```\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
