"""Events sent on the `POST /v1/chats/{id}/messages` stream.

Each SSE `data:` line is one JSON object of this union. The browser validates every event with
a schema generated from api/openapi/stream-events.schema.json and ignores unknown types.
"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, TypeAdapter

from cardwise_api.models import CardRef, Model


class StartEvent(Model):
    type: Literal["start"] = "start"
    message_id: UUID


class TextEvent(Model):
    type: Literal["text"] = "text"
    text: str


class ToolEvent(Model):
    """Progress for the UI ("Searching cards…"). Never carries tool arguments or results."""

    type: Literal["tool"] = "tool"
    name: Literal["search_cards", "get_card", "get_rulings", "similar_cards"]
    status: Literal["running", "done"]


class CardsEvent(Model):
    """Every card the answer may link to. Card refs not listed here render as plain text."""

    type: Literal["cards"] = "cards"
    cards: list[CardRef]


class UsageOut(Model):
    input_tokens: int
    output_tokens: int


class DoneEvent(Model):
    type: Literal["done"] = "done"
    message_id: UUID
    usage: UsageOut


class ErrorEvent(Model):
    type: Literal["error"] = "error"
    code: Literal["rate_limited", "model_unavailable", "internal"]
    request_id: str


StreamEvent = Annotated[
    StartEvent | TextEvent | ToolEvent | CardsEvent | DoneEvent | ErrorEvent,
    Field(discriminator="type"),
]

stream_event_adapter: TypeAdapter[StreamEvent] = TypeAdapter(StreamEvent)
