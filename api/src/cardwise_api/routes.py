"""HTTP routes. Bodies are stubs until line D; the signatures and models are the contract."""

from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from cardwise_api.models import (
    CardDetail,
    CardSearchPage,
    ChatCreate,
    ChatOut,
    ChatPage,
    ChatRename,
    Cursor,
    ErrorBody,
    Health,
    MessageCreate,
    MessagePage,
)

bearer = HTTPBearer(description="Supabase access token")
Credentials = Annotated[HTTPAuthorizationCredentials, Depends(bearer)]

ERRORS: dict[int | str, dict[str, object]] = {
    status: {"model": ErrorBody} for status in (401, 404, 422, 429, 500)
}

public = APIRouter()
v1 = APIRouter(prefix="/v1", responses=ERRORS)


def _not_implemented() -> NoReturn:
    raise HTTPException(status_code=501)


@public.get("/healthz", tags=["health"])
async def health() -> Health:
    return Health()


@v1.get("/chats", tags=["chats"])
async def list_chats(
    _: Credentials,
    cursor: Annotated[Cursor | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ChatPage:
    _not_implemented()


@v1.post("/chats", status_code=201, tags=["chats"])
async def create_chat(_: Credentials, body: ChatCreate) -> ChatOut:
    _not_implemented()


@v1.patch("/chats/{chat_id}", tags=["chats"])
async def rename_chat(_: Credentials, chat_id: UUID, body: ChatRename) -> ChatOut:
    _not_implemented()


@v1.delete("/chats/{chat_id}", status_code=204, tags=["chats"])
async def delete_chat(_: Credentials, chat_id: UUID) -> None:
    _not_implemented()


@v1.get("/chats/{chat_id}/messages", tags=["chats"])
async def list_messages(
    _: Credentials,
    chat_id: UUID,
    cursor: Annotated[Cursor | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> MessagePage:
    _not_implemented()


@v1.post(
    "/chats/{chat_id}/messages",
    tags=["chats"],
    responses={
        200: {
            "description": "Server-sent events. Each `data:` line is one StreamEvent "
            "(api/openapi/stream-events.schema.json).",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        }
    },
)
async def send_message(_: Credentials, chat_id: UUID, body: MessageCreate) -> None:
    _not_implemented()


@v1.get("/cards/search", tags=["cards"])
async def search_cards(
    _: Credentials,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> CardSearchPage:
    _not_implemented()


@v1.get("/cards/{oracle_id}", tags=["cards"])
async def get_card(_: Credentials, oracle_id: UUID) -> CardDetail:
    _not_implemented()
