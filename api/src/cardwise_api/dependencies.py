"""Request-scoped dependencies: the caller, a database connection and the services built on it.

Everything external hangs off `Services` on `app.state`, so tests swap in fakes either by
passing their own Services to `create_app` or with `app.dependency_overrides`. The chat model,
card backend factory and agent factory are None when not configured (no model API key, no
database); routes that need them then answer 501 without opening a connection.
"""

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated, Final

import asyncpg
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from cardwise_api.agent.loop import ChatAgent
from cardwise_api.agent.port import Agent, AgentFactory
from cardwise_api.auth import (
    AuthenticatedUser,
    AuthenticationError,
    JwksCache,
    JwksUnavailableError,
    TokenVerifier,
    http_jwks_fetcher,
)
from cardwise_api.chat_model import build_model
from cardwise_api.chats.repository import ChatRepository, PgChatRepository
from cardwise_api.db import Database
from cardwise_api.observability import user_hash
from cardwise_api.ratelimit import PgRateLimiter, RateLimiter
from cardwise_api.retrieval import BackendFactory, CardBackend, GrepSearchBackend
from cardwise_api.settings import Settings
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
    backend_factory: BackendFactory | None = None
    """Builds a card backend on one request's connection; None without a database."""
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
        return cls(
            settings=settings,
            verifier=verifier,
            database=Database(dsn),
            chat_model=build_model(settings),
            backend_factory=GrepSearchBackend if dsn is not None else None,
            agent_factory=ChatAgent,
        )


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


def require_backend_factory(services: ServicesDep) -> BackendFactory:
    if services.backend_factory is None:
        raise HTTPException(status_code=501)
    return services.backend_factory


@dataclass(frozen=True, slots=True)
class AgentParts:
    factory: AgentFactory
    model: ChatModel
    backend_factory: BackendFactory


def require_agent_parts(services: ServicesDep) -> AgentParts:
    if (
        services.agent_factory is None
        or services.chat_model is None
        or services.backend_factory is None
    ):
        raise HTTPException(status_code=501)
    return AgentParts(services.agent_factory, services.chat_model, services.backend_factory)


# FastAPI resolves dependencies in parameter order, so the 501 checks run before the
# connection is opened: an unconfigured feature costs no database round trip.
def get_card_backend(
    factory: Annotated[BackendFactory, Depends(require_backend_factory)], conn: Connection
) -> CardBackend:
    return factory(conn)


def get_agent(
    parts: Annotated[AgentParts, Depends(require_agent_parts)], conn: Connection
) -> Agent:
    """The agent's tools share the request's connection with the chat repository."""
    return parts.factory(parts.model, parts.backend_factory(conn))


Repo = Annotated[ChatRepository, Depends(get_chat_repo)]
Limiter = Annotated[RateLimiter, Depends(get_rate_limiter)]
AgentDep = Annotated[Agent, Depends(get_agent)]
CardBackendDep = Annotated[CardBackend, Depends(get_card_backend)]
