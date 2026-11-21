"""Write the committed API contract files the web client is generated from.

Run after an intentional contract change:  uv run python -m cardwise_api.export_schemas
"""

import json
from pathlib import Path

from cardwise_api.main import create_app
from cardwise_api.stream_events import stream_event_adapter

OPENAPI_DIR = Path(__file__).resolve().parents[2] / "openapi"


def _dump(data: object) -> str:
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def render() -> dict[str, str]:
    return {
        "openapi.json": _dump(create_app().openapi()),
        "stream-events.schema.json": _dump(stream_event_adapter.json_schema()),
    }


def main() -> None:
    OPENAPI_DIR.mkdir(exist_ok=True)
    for name, text in render().items():
        (OPENAPI_DIR / name).write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
