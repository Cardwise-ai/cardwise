"""Write the tool input JSON Schemas that tests compare against.

Run after an intentional contract change:  uv run python -m cardwise_core.schemas
"""

import json
from pathlib import Path

from cardwise_core.search import TOOL_INPUTS

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"


def render(name: str) -> str:
    return json.dumps(TOOL_INPUTS[name].model_json_schema(), indent=2, sort_keys=True) + "\n"


def main() -> None:
    SCHEMA_DIR.mkdir(exist_ok=True)
    for name in TOOL_INPUTS:
        (SCHEMA_DIR / f"{name}.json").write_text(render(name), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
