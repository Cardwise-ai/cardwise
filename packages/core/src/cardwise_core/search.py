"""The retrieval contract. grepRAG and vector backends both implement SearchBackend.

The query models double as the agent's tool inputs, so their field descriptions are what the
model reads. Keep them short and concrete.
"""

from typing import Annotated, Literal, Protocol, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cardwise_core.cards import MAX_CARD_NAME_LENGTH, Color, Format


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


TagSlug = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]{0,99}$")]
ShortText = Annotated[str, Field(min_length=1, max_length=40)]


class CardQuery(Model):
    """Find cards. Every filter that is set must match."""

    text: Annotated[str | None, Field(min_length=1, max_length=200)] = Field(
        default=None, description="Words to match in name, type line or rules text."
    )
    color_identity_within: frozenset[Color] | None = Field(
        default=None,
        description="Only cards a commander with these colors can include. Empty means colorless.",
    )
    colors_include: frozenset[Color] = Field(
        default=frozenset(), description="Card color identity must include all of these."
    )
    types: Annotated[tuple[ShortText, ...], Field(max_length=4)] = Field(
        default=(), description="Words the type line must contain, such as Creature or Elf."
    )
    keywords: Annotated[tuple[ShortText, ...], Field(max_length=5)] = Field(
        default=(), description="Keyword abilities the card must have, such as Flying."
    )
    tags: Annotated[tuple[TagSlug, ...], Field(max_length=5)] = Field(
        default=(), description="Scryfall Tagger oracle tags, such as ramp or sacrifice-outlet."
    )
    mana_value_min: Annotated[float, Field(ge=0, le=20)] | None = None
    mana_value_max: Annotated[float, Field(ge=0, le=20)] | None = None
    legal_in: Format | None = Field(default=None, description="Format the card must be legal in.")
    limit: Annotated[int, Field(ge=1, le=25)] = 10

    @model_validator(mode="after")
    def _check(self) -> Self:
        lo, hi = self.mana_value_min, self.mana_value_max
        if lo is not None and hi is not None and lo > hi:
            raise ValueError("mana_value_min is greater than mana_value_max")
        filters = self.model_dump(exclude={"limit", "legal_in"}, exclude_defaults=True)
        if not filters:
            raise ValueError("set at least one filter besides limit and legal_in")
        return self


class CardLookup(Model):
    """Get one card by exact Oracle ID or by name."""

    oracle_id: UUID | None = None
    name: Annotated[str, Field(min_length=1, max_length=MAX_CARD_NAME_LENGTH)] | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> Self:
        if (self.oracle_id is None) == (self.name is None):
            raise ValueError("give exactly one of oracle_id or name")
        return self


class RulingsLookup(Model):
    """Get official rulings for a card."""

    oracle_id: UUID


class SimilarQuery(Model):
    """Find cards similar to a given card."""

    oracle_id: UUID
    by: Literal["role", "text"] = Field(
        description="role: shares Tagger function tags. text: similar rules text."
    )
    color_identity_within: frozenset[Color] | None = None
    limit: Annotated[int, Field(ge=1, le=25)] = 10


class CardHit(Model):
    oracle_id: UUID
    name: str
    mana_cost: str
    """Empty for cards without a mana cost. Faces are joined with ' // '."""
    mana_value: float
    type_line: str
    oracle_text: str
    """Faces are joined with a blank line."""
    color_identity: tuple[Color, ...]
    image_uri: str | None
    """`normal` size image on cards.scryfall.io, front face for double-faced cards."""
    matched_tags: tuple[str, ...] = ()
    score: float


class SearchBackend(Protocol):
    @property
    def name(self) -> str:
        """Short identifier recorded with eval results, e.g. `grep` or `vector`."""
        ...

    async def search(self, query: CardQuery) -> list[CardHit]: ...

    async def similar(self, query: SimilarQuery) -> list[CardHit]: ...


TOOL_INPUTS: dict[str, type[BaseModel]] = {
    "search_cards": CardQuery,
    "get_card": CardLookup,
    "get_rulings": RulingsLookup,
    "similar_cards": SimilarQuery,
}
"""Tool name to input model. JSON Schemas are snapshot-tested in packages/core/schemas."""
