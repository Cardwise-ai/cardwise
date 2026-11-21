"""An in-memory CardBackend for agent and card endpoint tests (no database)."""

from collections.abc import Iterable, Mapping, Sequence
from uuid import NAMESPACE_URL, UUID, uuid5

import anyio
from pydantic import BaseModel

from cardwise_api.models import CardDetail, Ruling
from cardwise_core.cards import Color
from cardwise_core.search import CardHit, CardLookup, CardQuery, RulingsLookup, SimilarQuery


def card_id(name: str) -> UUID:
    """A stable oracle ID per name, so tests can refer to cards by name."""
    return uuid5(NAMESPACE_URL, f"cardwise-test:{name}")


def hit(
    name: str,
    *,
    type_line: str = "Creature",
    text: str = "",
    colors: Iterable[Color] = (),
    mana_cost: str = "{1}",
    mana_value: float = 1.0,
    image_uri: str | None = None,
) -> CardHit:
    return CardHit(
        oracle_id=card_id(name),
        name=name,
        mana_cost=mana_cost,
        mana_value=mana_value,
        type_line=type_line,
        oracle_text=text,
        color_identity=tuple(colors),
        image_uri=image_uri or f"https://cards.scryfall.io/normal/front/{card_id(name)}.jpg",
        score=1.0,
    )


class FakeCardBackend:
    """Matches words against name, type line and text; records every call.

    `max_active` counts calls running at the same time: the real backend shares one database
    connection, so the agent must never make it exceed 1.
    """

    def __init__(
        self,
        cards: Sequence[CardHit] = (),
        *,
        rulings: Mapping[UUID, list[Ruling]] | None = None,
        delay_s: float = 0.0,
    ) -> None:
        self.cards = list(cards)
        self.rulings = dict(rulings or {})
        self.delay_s = delay_s
        self.calls: list[tuple[str, BaseModel | str | UUID]] = []
        self.active = 0
        self.max_active = 0

    @property
    def name(self) -> str:
        return "fake"

    async def _enter(self, method: str, argument: BaseModel | str | UUID) -> None:
        self.calls.append((method, argument))
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await anyio.sleep(self.delay_s)
        finally:
            self.active -= 1

    def _matching(self, text: str | None, colors: frozenset[Color] | None) -> list[CardHit]:
        words = (text or "").casefold().split()
        found = []
        for card in self.cards:
            haystack = f"{card.name} {card.type_line} {card.oracle_text}".casefold()
            if not all(w in haystack for w in words):
                continue
            if colors is not None and not set(card.color_identity) <= colors:
                continue
            found.append(card)
        return found

    async def search(self, query: CardQuery) -> list[CardHit]:
        await self._enter("search", query)
        return self._matching(query.text, query.color_identity_within)[: query.limit]

    async def similar(self, query: SimilarQuery) -> list[CardHit]:
        await self._enter("similar", query)
        found = self._matching(None, query.color_identity_within)
        return [c for c in found if c.oracle_id != query.oracle_id][: query.limit]

    async def get_card(self, query: CardLookup) -> CardHit | None:
        await self._enter("get_card", query)
        for card in self.cards:
            if card.oracle_id == query.oracle_id or (
                query.name is not None and card.name.casefold() == query.name.casefold()
            ):
                return card
        return None

    async def get_rulings(self, query: RulingsLookup) -> list[Ruling]:
        await self._enter("get_rulings", query)
        return self.rulings.get(query.oracle_id, [])

    async def find(self, text: str, limit: int) -> list[CardHit]:
        await self._enter("find", text)
        return self._matching(text, None)[:limit]

    async def get_detail(self, oracle_id: UUID) -> CardDetail | None:
        await self._enter("get_detail", oracle_id)
        card = next((c for c in self.cards if c.oracle_id == oracle_id), None)
        if card is None:
            return None
        return CardDetail(
            oracle_id=card.oracle_id,
            name=card.name,
            layout="normal",
            mana_cost=card.mana_cost,
            mana_value=card.mana_value,
            type_line=card.type_line,
            oracle_text=card.oracle_text,
            color_identity=list(card.color_identity),
            keywords=[],
            legalities={"commander": "legal"},
            faces=[],
            tags=[],
            rulings=self.rulings.get(oracle_id, []),
            image_uri=card.image_uri,
            scryfall_uri=f"https://scryfall.com/card/test/{oracle_id}",
        )
