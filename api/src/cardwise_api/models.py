"""Request and response bodies for the HTTP API. This module is the API contract."""

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from cardwise_core.cards import Color


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


ChatTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
MessageText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)
]
Cursor = Annotated[str, StringConstraints(min_length=1, max_length=200)]


class ChatCreate(Model):
    title: ChatTitle | None = None
    """Defaults to "New chat"; the server may later rename it from the first message."""


class ChatRename(Model):
    title: ChatTitle


class ChatOut(Model):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ChatPage(Model):
    items: list[ChatOut]
    next_cursor: Cursor | None


class MessageCreate(Model):
    content: MessageText


class CardRef(Model):
    """A card the answer refers to. The name always comes from our corpus, never the model."""

    oracle_id: UUID
    name: str
    image_uri: str | None


class MessageOut(Model):
    id: UUID
    role: Literal["user", "assistant"]
    content: str
    status: Literal["complete", "interrupted", "failed"]
    cards: list[CardRef]
    created_at: datetime


class MessagePage(Model):
    items: list[MessageOut]
    next_cursor: Cursor | None


Legality = Literal["legal", "not_legal", "banned", "restricted"]


class CardFace(Model):
    name: str
    mana_cost: str
    type_line: str
    oracle_text: str
    power: str | None
    toughness: str | None
    loyalty: str | None
    defense: str | None
    image_uri: str | None


class TagRef(Model):
    slug: str
    label: str


class Ruling(Model):
    published_at: date
    source: Literal["wotc", "scryfall"]
    text: str


class CardDetail(Model):
    oracle_id: UUID
    name: str
    layout: str
    mana_cost: str
    mana_value: float
    type_line: str
    oracle_text: str
    color_identity: list[Color]
    keywords: list[str]
    legalities: dict[str, Legality]
    faces: list[CardFace]
    """Empty for single-faced cards."""
    tags: list[TagRef]
    rulings: list[Ruling]
    image_uri: str | None
    scryfall_uri: str


class CardSummary(Model):
    oracle_id: UUID
    name: str
    mana_cost: str
    type_line: str
    image_uri: str | None


class CardSearchPage(Model):
    items: list[CardSummary]


class Health(Model):
    status: Literal["ok"] = "ok"


ErrorCode = Literal[
    "bad_request",
    "unauthorized",
    "not_found",
    "rate_limited",
    "not_implemented",
    "internal",
]


class ErrorDetail(Model):
    code: ErrorCode
    message: str
    request_id: str
    fields: list[str] = Field(default_factory=list)
    """Names of invalid fields on bad_request. Never includes submitted values."""


class ErrorBody(Model):
    error: ErrorDetail
