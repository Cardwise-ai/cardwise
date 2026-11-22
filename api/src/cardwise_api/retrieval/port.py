"""What the API needs from card retrieval: the shared SearchBackend plus lookups.

A backend is built per request on that request's database connection, so one backend must
never run two calls at once (one asyncpg connection runs one query at a time).
"""

from collections.abc import Callable
from typing import Protocol
from uuid import UUID

import asyncpg

from cardwise_api.models import CardDetail, Ruling
from cardwise_core.search import CardHit, CardLookup, RulingsLookup, SearchBackend


class CardBackend(SearchBackend, Protocol):
    async def get_card(self, query: CardLookup) -> CardHit | None: ...

    async def get_rulings(self, query: RulingsLookup) -> list[Ruling]: ...

    async def find(self, text: str, limit: int) -> list[CardHit]:
        """Free-text search for the card panel."""
        ...

    async def get_detail(self, oracle_id: UUID) -> CardDetail | None: ...


BackendFactory = Callable[[asyncpg.Connection], CardBackend]
"""Builds the backend for one request from its database connection."""
