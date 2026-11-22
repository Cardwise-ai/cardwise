"""Structured JSON logs. One line per event, never message text, tokens or connection strings.

Log calls pass data as `extra={"fields": {...}}`; only those fields and the request ID are
written, so arbitrary record attributes (and whatever a library stuffed into them) stay out.
"""

import hashlib
import json
import logging
import sys
import time
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Final
from uuid import UUID

from starlette.types import ASGIApp, Message, Receive, Scope, Send

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

access_log: Final = logging.getLogger("cardwise_api.access")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        request_id = request_id_var.get()
        if request_id is not None:
            entry["request_id"] = request_id
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            entry.update(fields)
        if record.exc_info and record.exc_info[0] is not None:
            # The type only: exception messages can carry SQL, URLs or user text.
            entry["exc_type"] = record.exc_info[0].__name__
        return json.dumps(entry, default=str, separators=(",", ":"))


def configure_logging(level: str) -> None:
    root = logging.getLogger("cardwise_api")
    if not any(getattr(h, "_cardwise", False) for h in root.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        handler._cardwise = True  # type: ignore[attr-defined]
        root.addHandler(handler)
        root.propagate = False
    root.setLevel(level)


def user_hash(user_id: UUID) -> str:
    """A stable pseudonym for logs, so one user's requests can be grouped without the ID."""
    return hashlib.sha256(b"cardwise-user:" + user_id.bytes).hexdigest()[:16]


def _route_template(scope: Scope) -> str:
    # Included routers keep relative paths, so rebuild the full template from the
    # request path by swapping path-param values back for their names (no ids logged).
    names = {str(v): k for k, v in scope.get("path_params", {}).items()}
    segments = str(scope["path"]).split("/")
    return "/".join(f"{{{names[s]}}}" if s in names else s for s in segments)


class AccessLogMiddleware:
    """Logs method, route template, status and latency. Never the query string or body."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        status = 500

        async def send_and_record(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, send_and_record)
        finally:
            route = scope.get("route")
            state = scope.get("state", {})
            fields: dict[str, object] = {
                "method": scope["method"],
                "route": _route_template(scope) if route is not None else "unmatched",
                "status": status,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            }
            if "user_hash" in state:
                fields["user"] = state["user_hash"]
            access_log.info("request", extra={"fields": fields})
