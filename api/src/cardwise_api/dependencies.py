"""Request-scoped dependencies: the caller, a database connection and the services built on it.

Everything external hangs off `Services` on `app.state`, so tests swap in fakes either by
passing their own Services to `create_app` or with `app.dependency_overrides`. The chat model,
search backend and agent are None until lines D8/D9 and R1 provide them; routes that need
them answer 501 until then.
"""

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated, Final

import asyncpg
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from cardwise_api.agent.port import Agent, AgentFactory
from cardwise_api.auth import (
    AuthenticatedUser,
    AuthenticationError,
    JwksCache,
    JwksUnavailableError,
    TokenVerifier,
    http_jwks_fetcher,
)
from cardwise_api.chats.repository import ChatRepository, PgChatRepository
from cardwise_api.db import Database
from cardwise_api.observability import user_hash
from cardwise_api.ratelimit import PgRateLimiter, RateLimiter
from cardwise_api.settings import Settings
from cardwise_core.search import SearchBackend
from cardwise_llm import ChatModel

log: Final = logging.getLogger("cardwise_api.auth")

bearer = HTTPBearer(description="Supabase access token", auto_error=False)

_UNAUTHORIZED_HEADERS: Final = {"WWW-Authenticate": "Bearer"}


@dataclass(frozen=True, slots=True)
class Services:
    settings: Settings
    verifier: TokenVerifier | None
    database: Database
    chat_model: ChatModel | None = None
    search_backend: SearchBackend | None = None
    agent_factory: AgentFactory | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> "Services":
        verifier = None
        if settings.jwks_url is not None and settings.issuer is not None:
            keys = JwksCache(
                http_jwks_fetcher(settings.jwks_url),
                ttl_s=settings.jwks_cache_ttl_s,
                min_refresh_interval_s=settings.jwks_min_refresh_interval_s,
            )
            verifier = TokenVerifier(
                keys,
                issuer=settings.issuer,
                audience=settings.jwt_audience,
                leeway_s=settings.jwt_leeway_s,
            )
        dsn = settings.database_url.get_secret_value() if settings.database_url else None
        return cls(settings=settings, verifier=verifier, database=Database(dsn))


def get_services(request: Request) -> Services:
    services: Services = request.app.state.services
    return services


ServicesDep = Annotated[Services, Depends(get_services)]


async def current_user(
    request: Request,
    services: ServicesDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> AuthenticatedUser:
    if credentials is None or services.verifier is None:
        raise HTTPException(status_code=401, headers=_UNAUTHORIZED_HEADERS)
    try:
        user = await services.verifier.verify(credentials.credentials)
    except AuthenticationError as exc:
        log.info("token rejected", extra={"fields": {"reason": str(exc)}})
        raise HTTPException(status_code=401, headers=_UNAUTHORIZED_HEADERS) from exc
    except JwksUnavailableError as exc:
        log.error("JWKS unavailable", exc_info=exc)
        raise HTTPException(status_code=503) from exc
    request.state.user_hash = user_hash(user.id)
    return user


CurrentUser = Annotated[AuthenticatedUser, Depends(current_user)]


async def get_db(services: ServicesDep) -> AsyncIterator[asyncpg.Connection]:
    """One connection per request, closed after the response (streams included) has finished."""
    async with services.database.connect() as conn:
        yield conn


Connection = Annotated[asyncpg.Connection, Depends(get_db)]


def get_chat_repo(conn: Connection) -> ChatRepository:
    return PgChatRepository(conn)


def get_rate_limiter(conn: Connection, services: ServicesDep) -> RateLimiter:
    s = services.settings
    return PgRateLimiter(
        conn,
        messages_per_hour=s.messages_per_hour,
        concurrent_streams=s.concurrent_streams,
        lease_s=s.stream_lease_s,
    )


def get_chat_model(services: ServicesDep) -> ChatModel:
    if services.chat_model is None:
        raise HTTPException(status_code=501)
    return services.chat_model


def get_search_backend(services: ServicesDep) -> SearchBackend:
    if services.search_backend is None:
        raise HTTPException(status_code=501)
    return services.search_backend


def get_agent(services: ServicesDep) -> Agent:
    # Checked before the model and backend so an unbuilt agent costs no other setup.
    if services.agent_factory is None:
        raise HTTPException(status_code=501)
    return services.agent_factory(get_chat_model(services), get_search_backend(services))


Repo = Annotated[ChatRepository, Depends(get_chat_repo)]
Limiter = Annotated[RateLimiter, Depends(get_rate_limiter)]
AgentDep = Annotated[Agent, Depends(get_agent)]
SearchBackendDep = Annotated[SearchBackend, Depends(get_search_backend)]
