"""Route assembly: health, the chat routes and the card endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from cardwise_api.chats.routes import router as chat_router
from cardwise_api.dependencies import CardBackendDep, CurrentUser
from cardwise_api.models import CardDetail, CardSearchPage, CardSummary, ErrorBody, Health

ERRORS: dict[int | str, dict[str, object]] = {
    status: {"model": ErrorBody} for status in (401, 404, 422, 429, 500)
}

public = APIRouter()
v1 = APIRouter(prefix="/v1", responses=ERRORS)


@public.get("/healthz", tags=["health"])
async def health() -> Health:
    """Liveness only: no database or JWKS call, so it stays cheap and always answers."""
    return Health()


cards = APIRouter(tags=["cards"])


@cards.get("/cards/search")
async def search_cards(
    _: CurrentUser,
    backend: CardBackendDep,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> CardSearchPage:
    """Cards matching words in their name, type line or rules text, best match first."""
    hits = await backend.find(q, limit)
    return CardSearchPage(
        items=[
            CardSummary(
                oracle_id=hit.oracle_id,
                name=hit.name,
                mana_cost=hit.mana_cost,
                type_line=hit.type_line,
                image_uri=hit.image_uri,
            )
            for hit in hits
        ]
    )


@cards.get("/cards/{oracle_id}")
async def get_card(_: CurrentUser, backend: CardBackendDep, oracle_id: UUID) -> CardDetail:
    """Card panel data from the current corpus snapshot."""
    card = await backend.get_detail(oracle_id)
    if card is None:
        raise HTTPException(status_code=404)
    return card


v1.include_router(chat_router)
v1.include_router(cards)
