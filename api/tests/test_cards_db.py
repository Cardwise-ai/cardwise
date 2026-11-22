"""Card panel queries against the ingest fixture corpus. Run `supabase db start` first."""

from uuid import UUID, uuid4

import pytest

from cardwise_api.retrieval import GrepSearchBackend

pytestmark = pytest.mark.db

LLANOWAR = UUID("68954295-54e3-4303-a6bc-fc4547a4e3a3")
FALLAJI = UUID("01de1f9d-3b63-49b9-b2c6-929c2a69ef54")
DELVER = UUID("edd531b9-f615-4399-8c8c-1c5e18c4acbf")


async def test_a_single_faced_creature_has_its_stats(backend: GrepSearchBackend) -> None:
    card = await backend.get_detail(LLANOWAR)
    assert card is not None
    assert (card.name, card.layout, card.power, card.toughness) == (
        "Llanowar Elves",
        "normal",
        "1",
        "1",
    )
    assert card.faces == []
    assert card.legalities["commander"] == "legal"
    assert card.image_uri is not None
    assert card.scryfall_uri.startswith("https://scryfall.com/")


async def test_a_double_faced_card_has_its_faces(backend: GrepSearchBackend) -> None:
    card = await backend.get_detail(DELVER)
    assert card is not None
    assert [f.name for f in card.faces] == ["Delver of Secrets", "Insectile Aberration"]
    assert (card.faces[1].power, card.faces[1].toughness) == ("3", "2")
    assert all(f.image_uri for f in card.faces)


async def test_rulings_come_oldest_first(backend: GrepSearchBackend) -> None:
    card = await backend.get_detail(FALLAJI)
    assert card is not None
    assert len(card.rulings) >= 3
    dates = [r.published_at for r in card.rulings]
    assert dates == sorted(dates)
    assert {r.source for r in card.rulings} == {"wotc"}


async def test_an_unknown_card_is_none(backend: GrepSearchBackend) -> None:
    assert await backend.get_detail(uuid4()) is None


async def test_find_matches_names_and_allows_large_pages(backend: GrepSearchBackend) -> None:
    hits = await backend.find("llanowar", 50)
    assert [h.name for h in hits][:1] == ["Llanowar Elves"]
    assert len(await backend.find("a", 30)) <= 30
