"""GrepSearchBackend against the ingest fixture corpus. Run `supabase db start` first."""

import json
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import asyncpg
import pytest

from cardwise_api.retrieval import GrepSearchBackend
from cardwise_core.cards import Color, Format
from cardwise_core.search import CardHit, CardLookup, CardQuery, RulingsLookup, SimilarQuery

pytestmark = pytest.mark.db

SEED_QUERIES: list[dict[str, Any]] = json.loads(
    (Path(__file__).parent / "fixtures" / "seed_queries.json").read_text("utf-8")
)

CULTIVATE = UUID("8b755881-a72d-4e21-a369-d2924eb4585a")
LLANOWAR = UUID("68954295-54e3-4303-a6bc-fc4547a4e3a3")
INVASION = UUID("4b1874af-4ea5-4e22-a4d4-e718d75fe95e")
INVASION_NAME = "Invasion of Zendikar // Awakened Skyclave"


def names(hits: list[CardHit]) -> list[str]:
    return [h.name for h in hits]


async def test_structured_filters(backend: GrepSearchBackend) -> None:
    green_creatures = names(
        await backend.search(
            CardQuery(types=("Creature",), color_identity_within=frozenset({Color.GREEN}))
        )
    )
    assert {"Llanowar Elves", "Fallaji Wayfarer", INVASION_NAME} <= set(green_creatures)
    assert "Bruna, the Fading Light" not in green_creatures

    fliers = names(await backend.search(CardQuery(keywords=("flying",))))
    assert sorted(fliers) == [
        "Bruna, the Fading Light",
        "Delver of Secrets // Insectile Aberration",
    ]

    three_drops = await backend.search(CardQuery(mana_value_min=3, mana_value_max=3))
    assert {h.mana_value for h in three_drops} == {3.0}
    assert "Cultivate" in names(three_drops)

    artifacts = names(
        await backend.search(CardQuery(types=("Artifact",), legal_in=Format.COMMANDER))
    )
    assert artifacts == ["Sol Ring"]

    # Tokens are stored but never searched.
    assert names(await backend.search(CardQuery(types=("Goblin",)))) == [
        "Akki Lavarunner // Tok-Tok, Volcano Born"
    ]

    limited = await backend.search(CardQuery(types=("Creature",), limit=2))
    assert len(limited) == 2
    assert [h.score for h in limited] == sorted((h.score for h in limited), reverse=True)


async def test_hits_carry_card_fields(backend: GrepSearchBackend) -> None:
    [fire_ice] = await backend.search(CardQuery(text="Fire // Ice", limit=1))
    assert fire_ice.name == "Fire // Ice"
    assert fire_ice.color_identity == (Color.BLUE, Color.RED)
    assert fire_ice.mana_cost == "{1}{R} // {1}{U}"
    assert fire_ice.image_uri is not None
    assert fire_ice.image_uri.startswith("https://cards.scryfall.io/normal/")


async def test_tags_include_descendant_tags(backend: GrepSearchBackend) -> None:
    ramp = await backend.search(CardQuery(tags=("ramp",)))
    # No card is tagged `ramp` directly; all of these come from descendants.
    assert sorted(names(ramp)) == [
        "Cultivate",
        "Fallaji Wayfarer",
        INVASION_NAME,
        "Llanowar Elves",
        "Sol Ring",
    ]
    by_name = {h.name: h for h in ramp}
    assert by_name["Sol Ring"].matched_tags == ("mana-rock",)
    assert by_name[INVASION_NAME].matched_tags == (
        "mana-dork",
        "multi-land-ramp",
        "ramp-with-set-s-mechanic",
    )

    both = await backend.search(CardQuery(tags=("ramp", "tutor")))
    assert sorted(names(both)) == ["Cultivate", INVASION_NAME]


async def test_retired_snapshot_is_never_read(
    backend: GrepSearchBackend, retired_only: tuple[UUID, str]
) -> None:
    oracle_id, name = retired_only
    assert await backend.search(CardQuery(text=name)) == []
    assert names(await backend.search(CardQuery(tags=("mana-rock",)))) == ["Sol Ring"]
    assert names(await backend.search(CardQuery(text="sol ring"))).count("Sol Ring") == 1
    assert await backend.get_card(CardLookup(oracle_id=oracle_id)) is None
    assert await backend.get_card(CardLookup(name=name)) is None
    similar = await backend.similar(
        SimilarQuery(oracle_id=LLANOWAR, by="role", color_identity_within=frozenset())
    )
    assert oracle_id not in {h.oracle_id for h in similar}


@pytest.mark.parametrize(
    ("name", "expected", "score"),
    [
        ("Sol Ring", "Sol Ring", 1.0),
        ("sol ring", "Sol Ring", 0.95),
        ("Stomp", "Bonecrusher Giant // Stomp", 0.9),
        ("Lanowar Elves", "Llanowar Elves", None),
        ("kozilek", "Kozilek, Butcher of Truth", None),
    ],
)
async def test_get_card_by_name(
    backend: GrepSearchBackend, name: str, expected: str, score: float | None
) -> None:
    hit = await backend.get_card(CardLookup(name=name))
    assert hit is not None
    assert hit.name == expected
    if score is None:
        assert 0 < hit.score < 0.9
    else:
        assert hit.score == score


async def test_get_card_by_id_and_misses(backend: GrepSearchBackend) -> None:
    hit = await backend.get_card(CardLookup(oracle_id=CULTIVATE))
    assert hit is not None
    assert hit.name == "Cultivate"
    assert await backend.get_card(CardLookup(name="Qwxzv Plmkj")) is None
    assert await backend.get_card(CardLookup(oracle_id=UUID(int=1))) is None


async def test_rulings(backend: GrepSearchBackend) -> None:
    assert len(await backend.get_rulings(RulingsLookup(oracle_id=CULTIVATE))) == 1
    invasion = await backend.get_rulings(RulingsLookup(oracle_id=INVASION))
    assert len(invasion) == 18
    assert [r.published_at for r in invasion] == sorted(r.published_at for r in invasion)
    assert await backend.get_rulings(RulingsLookup(oracle_id=UUID(int=1))) == []


async def test_similar_by_role(backend: GrepSearchBackend) -> None:
    hits = await backend.similar(SimilarQuery(oracle_id=LLANOWAR, by="role"))
    found = names(hits)
    assert "Llanowar Elves" not in found
    assert {"Fallaji Wayfarer", INVASION_NAME} <= set(found[:3])
    # Sol Ring is a mana rock, not a dork; they meet at the parent tag mana-producer.
    sol_ring = next(h for h in hits if h.name == "Sol Ring")
    assert "mana-producer" in sol_ring.matched_tags
    assert all(0 < h.score <= 1 for h in hits)

    colorless = await backend.similar(
        SimilarQuery(oracle_id=LLANOWAR, by="role", color_identity_within=frozenset())
    )
    assert "Sol Ring" in names(colorless)
    assert all(h.color_identity == () for h in colorless)


async def test_similar_by_text(backend: GrepSearchBackend) -> None:
    hits = await backend.similar(SimilarQuery(oracle_id=CULTIVATE, by="text", limit=3))
    assert hits[0].name == INVASION_NAME
    assert "Cultivate" not in names(hits)


async def test_similar_by_text_with_lexeme_stats(
    corpus_db: asyncpg.Connection, backend: GrepSearchBackend
) -> None:
    # With planner stats, candidates come from the rarer lexemes only.
    await corpus_db.execute("analyze corpus.cards")
    hits = await backend.similar(SimilarQuery(oracle_id=CULTIVATE, by="text", limit=3))
    assert hits[0].name == INVASION_NAME
    assert "Cultivate" not in names(hits)


@pytest.mark.parametrize("by", ["role", "text"])
async def test_similar_limit_keeps_the_ranking(
    backend: GrepSearchBackend, by: Literal["role", "text"]
) -> None:
    full = await backend.similar(SimilarQuery(oracle_id=LLANOWAR, by=by, limit=25))
    assert len(full) > 3
    for limit in (1, 2, 3):
        hits = await backend.similar(SimilarQuery(oracle_id=LLANOWAR, by=by, limit=limit))
        assert names(hits) == names(full[:limit])


@pytest.mark.parametrize("seed", SEED_QUERIES, ids=[s["id"] for s in SEED_QUERIES])
async def test_seed_queries(backend: GrepSearchBackend, seed: dict[str, Any]) -> None:
    query = CardQuery.model_validate(seed["query"])
    found = names(await backend.search(query))
    if seed.get("empty"):
        assert found == []
        return
    assert found, seed["question"]
    assert set(seed["expect"]) <= set(found), found
    assert not set(seed.get("exclude", [])) & set(found), found
    if "first" in seed:
        assert found[0] == seed["first"]
