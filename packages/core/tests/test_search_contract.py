from uuid import UUID

import pytest
from pydantic import ValidationError

from cardwise_core.cards import Color, Format
from cardwise_core.schemas import SCHEMA_DIR, render
from cardwise_core.search import TOOL_INPUTS, CardLookup, CardQuery

SOME_ID = UUID("c8be6da5-4ec2-4a74-a3c5-7d7a76d4c76b")


@pytest.mark.parametrize("name", sorted(TOOL_INPUTS))
def test_tool_schemas_match_the_committed_snapshot(name: str) -> None:
    committed = (SCHEMA_DIR / f"{name}.json").read_text(encoding="utf-8")
    assert render(name) == committed, (
        f"{name} schema changed. If intended, run: uv run python -m cardwise_core.schemas"
    )


def test_query_parses_the_json_a_model_would_send() -> None:
    query = CardQuery.model_validate(
        {
            "text": "untap all creatures",
            "color_identity_within": ["G", "W"],
            "legal_in": "commander",
            "mana_value_max": 4,
        }
    )
    assert query.color_identity_within == frozenset({Color.GREEN, Color.WHITE})
    assert query.legal_in is Format.COMMANDER


def test_colorless_identity_is_an_empty_set_not_missing() -> None:
    query = CardQuery(types=("Artifact",), color_identity_within=frozenset())
    assert query.color_identity_within == frozenset()


def test_query_needs_a_real_filter() -> None:
    with pytest.raises(ValidationError, match="at least one filter"):
        CardQuery(legal_in=Format.COMMANDER, limit=5)


def test_query_rejects_inverted_mana_range_and_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="greater than"):
        CardQuery(text="draw", mana_value_min=5, mana_value_max=2)
    with pytest.raises(ValidationError):
        CardQuery.model_validate({"text": "draw", "sql": "drop table cards"})


@pytest.mark.parametrize("tag", ["Ramp", "ramp tag", "-ramp", "a" * 101])
def test_query_rejects_malformed_tags(tag: str) -> None:
    with pytest.raises(ValidationError):
        CardQuery(tags=(tag,))


def test_lookup_takes_exactly_one_key() -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        CardLookup()
    with pytest.raises(ValidationError, match="exactly one"):
        CardLookup(oracle_id=SOME_ID, name="Obeka, Splitter of Seconds")
    assert CardLookup(name="Obeka, Splitter of Seconds").oracle_id is None
