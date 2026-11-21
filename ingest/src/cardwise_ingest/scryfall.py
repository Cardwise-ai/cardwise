"""Pydantic models for the Scryfall bulk files we read.

Unknown fields are ignored: Scryfall adds fields without notice and that must not break a run.
Fields we rely on are validated strictly; a line that fails goes to quarantine.
"""

from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, HttpUrl

from cardwise_core.cards import Color

BulkType = Literal["oracle_cards", "rulings", "oracle_tags"]
BULK_TYPES: tuple[BulkType, ...] = ("oracle_cards", "rulings", "oracle_tags")

Legality = Literal["legal", "not_legal", "banned", "restricted"]
TagWeight = Literal["median", "strong", "very_strong"]
TAG_SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"
"""Same rule as the corpus.tags check constraint."""

Name = Annotated[str, Field(min_length=1, max_length=300)]


def _scryfall_data_url(url: HttpUrl) -> HttpUrl:
    if url.scheme != "https" or url.host != "data.scryfall.io":
        raise ValueError(f"bulk files must come from https://data.scryfall.io, got {url}")
    return url


class Input(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class BulkItem(Input):
    type: str
    updated_at: datetime
    jsonl_download_uri: Annotated[HttpUrl, AfterValidator(_scryfall_data_url)] | None = None
    compressed_size: int | None = None


class BulkIndex(Input):
    data: tuple[BulkItem, ...]


class ScryfallFace(Input):
    name: Name
    mana_cost: str = ""
    type_line: str | None = None
    oracle_text: str = ""
    colors: tuple[Color, ...] | None = None
    power: str | None = None
    toughness: str | None = None
    loyalty: str | None = None
    defense: str | None = None
    image_uris: dict[str, str] | None = None


class ScryfallCard(Input):
    oracle_id: UUID
    name: Name
    layout: Annotated[str, Field(min_length=1)]
    mana_cost: str | None = None
    """Missing on cards whose faces each have a cost (transform, modal DFC)."""
    cmc: Annotated[float, Field(ge=0)]
    type_line: Annotated[str, Field(min_length=1)]
    oracle_text: str | None = None
    """Missing on every multi-face card; the text lives on the faces."""
    colors: tuple[Color, ...] | None = None
    color_identity: tuple[Color, ...]
    keywords: tuple[str, ...]
    legalities: dict[str, Legality]
    image_uris: dict[str, str] | None = None
    scryfall_uri: Annotated[str, Field(pattern=r"^https://scryfall\.com/")]
    edhrec_rank: Annotated[int, Field(ge=1)] | None = None
    released_at: date
    card_faces: tuple[ScryfallFace, ...] = ()


class ScryfallRuling(Input):
    oracle_id: UUID
    source: Literal["wotc", "scryfall"]
    published_at: date
    comment: Annotated[str, Field(min_length=1)]


class Tagging(Input):
    oracle_id: UUID
    weight: TagWeight
    annotation: str | None = None


class OracleTag(Input):
    id: UUID
    slug: Annotated[str, Field(pattern=TAG_SLUG_PATTERN, max_length=100)]
    label: Annotated[str, Field(min_length=1)]
    type: Literal["oracle"]
    description: str | None = None
    aliases: tuple[str, ...] = ()
    parent_ids: tuple[UUID, ...] = ()
    child_ids: tuple[UUID, ...] = ()
    taggings: tuple[dict[str, Any], ...] = ()
    """Validated one by one as `Tagging`, so one bad tagging does not drop the whole tag."""
