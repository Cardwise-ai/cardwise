"""Route assembly: health, the chat routes and the card endpoints (stubs until D5)."""

from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from cardwise_api.chats.routes import router as chat_router
from cardwise_api.dependencies import CurrentUser
from cardwise_api.models import CardDetail, CardSearchPage, ErrorBody, Health

ERRORS: dict[int | str, dict[str, object]] = {
    status: {"model": ErrorBody} for status in (401, 404, 422, 429, 500)
}

public = APIRouter()
v1 = APIRouter(prefix="/v1", responses=ERRORS)


def _not_implemented() -> NoReturn:
    raise HTTPException(status_code=501)


@public.get("/healthz", tags=["health"])
async def health() -> Health:
    """Liveness only: no database or JWKS call, so it stays cheap and always answers."""
    return Health()


cards = APIRouter(tags=["cards"])


@cards.get("/cards/search")
async def search_cards(
    _: CurrentUser,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> CardSearchPage:
    _not_implemented()


@cards.get("/cards/{oracle_id}")
async def get_card(_: CurrentUser, oracle_id: UUID) -> CardDetail:
    _not_implemented()


v1.include_router(chat_router)
v1.include_router(cards)
