"""Chat routes. A chat owned by someone else answers 404, exactly like a missing one."""

from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError

from cardwise_api.chats.repository import InvalidCursorError, Position
from cardwise_api.chats.service import HISTORY_LIMIT, Turn, run_turn
from cardwise_api.dependencies import AgentDep, CurrentUser, Limiter, Repo, ServicesDep
from cardwise_api.errors import request_id
from cardwise_api.models import (
    ChatCreate,
    ChatOut,
    ChatPage,
    ChatRename,
    Cursor,
    MessageCreate,
    MessagePage,
)
from cardwise_api.ratelimit import RateLimitedError
from cardwise_api.streaming import EventStreamResponse

DEFAULT_TITLE = "New chat"

router = APIRouter(tags=["chats"])


def _not_found() -> NoReturn:
    raise HTTPException(status_code=404)


def _rate_limited(exc: RateLimitedError) -> NoReturn:
    raise HTTPException(status_code=429, headers={"Retry-After": str(exc.retry_after_s)})


def _position(cursor: str | None) -> Position | None:
    if cursor is None:
        return None
    try:
        return Position.decode(cursor)
    except InvalidCursorError as exc:
        raise RequestValidationError(
            [{"type": "value_error", "loc": ("query", "cursor"), "msg": "invalid cursor"}]
        ) from exc


@router.get("/chats")
async def list_chats(
    user: CurrentUser,
    repo: Repo,
    cursor: Annotated[Cursor | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ChatPage:
    """The caller's chats, most recently active first."""
    return await repo.list_chats(user.id, _position(cursor), limit)


@router.post("/chats", status_code=201)
async def create_chat(user: CurrentUser, repo: Repo, body: ChatCreate) -> ChatOut:
    return await repo.create_chat(user.id, body.title or DEFAULT_TITLE)


@router.get("/chats/{chat_id}")
async def get_chat(user: CurrentUser, repo: Repo, chat_id: UUID) -> ChatOut:
    chat = await repo.get_chat(user.id, chat_id)
    if chat is None:
        _not_found()
    return chat


@router.patch("/chats/{chat_id}")
async def rename_chat(user: CurrentUser, repo: Repo, chat_id: UUID, body: ChatRename) -> ChatOut:
    chat = await repo.rename_chat(user.id, chat_id, body.title)
    if chat is None:
        _not_found()
    return chat


@router.delete("/chats/{chat_id}", status_code=204)
async def delete_chat(user: CurrentUser, repo: Repo, chat_id: UUID) -> None:
    """Deletes the chat with its messages."""
    if not await repo.delete_chat(user.id, chat_id):
        _not_found()


@router.get("/chats/{chat_id}/messages")
async def list_messages(
    user: CurrentUser,
    repo: Repo,
    chat_id: UUID,
    cursor: Annotated[Cursor | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> MessagePage:
    """Messages oldest first; `next_cursor` continues forward in time."""
    page = await repo.list_messages(user.id, chat_id, _position(cursor), limit)
    if page is None:
        _not_found()
    return page


@router.post(
    "/chats/{chat_id}/messages",
    response_model=None,
    responses={
        200: {
            "description": "Server-sent events. Each `data:` line is one StreamEvent "
            "(api/openapi/stream-events.schema.json).",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        }
    },
)
async def send_message(
    request: Request,
    user: CurrentUser,
    agent: AgentDep,
    services: ServicesDep,
    repo: Repo,
    limiter: Limiter,
    chat_id: UUID,
    body: MessageCreate,
) -> EventStreamResponse:
    """Saves the message and streams the answer. Limits: 20 messages an hour, one stream."""
    history = await repo.recent_messages(user.id, chat_id, HISTORY_LIMIT)
    if history is None:
        _not_found()
    try:
        lease = await limiter.acquire_stream(user.id)
    except RateLimitedError as exc:
        _rate_limited(exc)
    try:
        await limiter.count_message(user.id)
        if await repo.add_user_message(user.id, chat_id, body.content) is None:
            _not_found()  # deleted since the check above
    except BaseException as exc:
        await limiter.release_stream(lease)
        if isinstance(exc, RateLimitedError):
            _rate_limited(exc)
        raise
    turn = Turn(
        user_id=user.id,
        chat_id=chat_id,
        history=history,
        question=body.content,
        agent=agent,
        repo=repo,
        limiter=limiter,
        lease=lease,
        request_id=request_id(request),
    )
    return EventStreamResponse(run_turn(turn), heartbeat_s=services.settings.heartbeat_s)
