"""Query building for the grep backend. No database; see test_grep_backend_db.py for results."""

import re
from decimal import Decimal
from typing import cast
from uuid import UUID

import pytest

from cardwise_api.retrieval import Executor, GrepSearchBackend
from cardwise_api.retrieval.grep_backend import (
    Statement,
    build_lookup,
    build_rulings,
    build_search,
    build_similar,
    type_words,
)
from cardwise_core.cards import Color, Format
from cardwise_core.search import (
    CardLookup,
    CardQuery,
    RulingsLookup,
    SearchBackend,
    SimilarQuery,
)

SOME_ID = UUID("8b755881-a72d-4e21-a369-d2924eb4585a")
NASTY = "'; drop table corpus.cards; --"


def placeholders(statement: Statement) -> set[int]:
    return {int(n) for n in re.findall(r"\$(\d+)", statement.sql)}


def assert_well_formed(statement: Statement) -> None:
    assert placeholders(statement) == set(range(1, len(statement.params) + 1))
    assert "where status = 'active'" in statement.sql


def test_backend_satisfies_the_protocol() -> None:
    backend: SearchBackend = GrepSearchBackend(cast(Executor, None))
    assert backend.name == "grep"


def test_every_filter_becomes_a_bind_parameter() -> None:
    query = CardQuery(
        text=NASTY,
        color_identity_within=frozenset({Color.GREEN, Color.WHITE}),
        colors_include=frozenset({Color.GREEN}),
        types=("Legendary Creature",),
        keywords=("Flying", "first strike"),
        tags=("ramp",),
        mana_value_min=0.5,
        mana_value_max=4,
        legal_in=Format.COMMANDER,
        limit=7,
    )
    statement = build_search(query)
    assert_well_formed(statement)
    assert NASTY not in statement.sql
    params = list(statement.params)
    assert params[0] == NASTY
    assert ["W", "G"] in params
    assert ["G"] in params
    assert ["creature", "legendary"] in params
    assert ["first strike", "flying"] in params
    assert Decimal("0.5") in params
    assert Decimal("4.0") in params
    assert "commander" in params
    assert params[-1] == 7


def test_search_without_text_or_tags_skips_their_ctes() -> None:
    statement = build_search(CardQuery(types=("Artifact",)))
    assert_well_formed(statement)
    assert "recursive" not in statement.sql
    assert "tsquery" not in statement.sql
    assert "'{}'::text[] as matched_tags" in statement.sql


def test_tags_expand_through_the_hierarchy_and_must_all_match() -> None:
    statement = build_search(CardQuery(tags=("ramp", "tutor", "ramp")))
    assert_well_formed(statement)
    assert statement.sql.startswith("with recursive ")
    assert "corpus.tag_parents" in statement.sql
    assert statement.params[0] == ["ramp", "tutor"]
    assert statement.params[1] == 2  # distinct tags every card must have
    assert "th.slugs as matched_tags" in statement.sql


def test_colorless_identity_filters_on_an_empty_set() -> None:
    statement = build_search(CardQuery(types=("Artifact",), color_identity_within=frozenset()))
    assert "c.color_identity <@ $1::text[]" in statement.sql
    assert statement.params[0] == []


@pytest.mark.parametrize(
    ("types", "words"),
    [
        (["Legendary Creature"], ["creature", "legendary"]),
        (["Creature — Elf Druid"], ["creature", "druid", "elf"]),
        (["Urza's", "elf"], ["elf", "urza's"]),
    ],
)
def test_type_words(types: list[str], words: list[str]) -> None:
    assert type_words(types) == words


def test_similar_picks_the_axis_and_optional_color_filter() -> None:
    role = build_similar(SimilarQuery(oracle_id=SOME_ID, by="role"))
    text = build_similar(
        SimilarQuery(oracle_id=SOME_ID, by="text", color_identity_within=frozenset({Color.RED}))
    )
    for statement in (role, text):
        assert_well_formed(statement)
        assert statement.params[0] == SOME_ID
    assert "corpus.card_tags" in role.sql
    assert "color_identity <@" not in role.sql
    assert "tsquery" in text.sql
    assert text.params[1] == ["R"]


def test_lookup_by_id_and_by_name() -> None:
    by_id = build_lookup(CardLookup(oracle_id=SOME_ID))
    by_name = build_lookup(CardLookup(name=NASTY))
    for statement in (by_id, by_name):
        assert_well_formed(statement)
    assert by_id.params == (SOME_ID,)
    assert by_name.params == (NASTY,)
    assert NASTY not in by_name.sql
    assert "corpus.card_faces" in by_name.sql
    assert "extensions.%" in by_name.sql


def test_rulings_are_scoped_to_the_active_snapshot() -> None:
    statement = build_rulings(RulingsLookup(oracle_id=SOME_ID))
    assert_well_formed(statement)
    assert statement.params == (SOME_ID,)
