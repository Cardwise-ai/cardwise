"""Test doubles for the API: local signing keys, a fake JWKS, a scripted agent and an app wired
to in-memory storage. Used by api/tests and available to later lines (agent, evals).

Keys are generated at runtime and never stored, so nothing secret lands in the repo.
"""

import time
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import jwt
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jwt.algorithms import ECAlgorithm, RSAAlgorithm

from cardwise_api.agent.port import Agent, AgentEvent, AgentRequest, AgentUsage
from cardwise_api.auth import JwksCache, TokenVerifier
from cardwise_api.chats.repository import InMemoryChatRepository, InMemoryChatStore
from cardwise_api.db import Database
from cardwise_api.dependencies import Services, get_agent, get_chat_repo, get_rate_limiter
from cardwise_api.main import create_app
from cardwise_api.ratelimit import InMemoryRateLimiter
from cardwise_api.settings import Settings
from cardwise_api.stream_events import TextEvent

SUPABASE_URL = "https://test-project.supabase.co"
ISSUER = f"{SUPABASE_URL}/auth/v1"
WEB_ORIGIN = "https://cardwise.example"


@dataclass(frozen=True)
class SigningKey:
    kid: str
    alg: str
    private: Any
    jwk: dict[str, object]


def ec_key(kid: str = "ec-1") -> SigningKey:
    private = ec.generate_private_key(ec.SECP256R1())
    jwk = ECAlgorithm.to_jwk(private.public_key(), as_dict=True)
    return SigningKey(kid, "ES256", private, {**jwk, "kid": kid, "alg": "ES256", "use": "sig"})


def rsa_key(kid: str = "rsa-1") -> SigningKey:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = RSAAlgorithm.to_jwk(private.public_key(), as_dict=True)
    return SigningKey(kid, "RS256", private, {**jwk, "kid": kid, "alg": "RS256", "use": "sig"})


@dataclass
class FakeJwks:
    """The project's JWKS endpoint. Tests add or rotate keys and count fetches."""

    keys: list[SigningKey]
    fetches: int = 0

    async def __call__(self) -> Mapping[str, object]:
        self.fetches += 1
        return {"keys": [k.jwk for k in self.keys]}


@dataclass(frozen=True)
class Tokens:
    """Mints Supabase-shaped access tokens. Pass a claim as None to leave it out."""

    key: SigningKey

    def mint(
        self,
        sub: UUID | str | None = None,
        *,
        key: SigningKey | None = None,
        headers: dict[str, Any] | None = None,
        **claims: object,
    ) -> str:
        signer = key or self.key
        now = int(time.time())
        payload: dict[str, object] = {
            "sub": str(sub or uuid4()),
            "iss": ISSUER,
            "aud": "authenticated",
            "iat": now,
            "exp": now + 3600,
            "role": "authenticated",
            "is_anonymous": False,
        }
        payload.update(claims)
        payload = {k: v for k, v in payload.items() if v is not None}
        return jwt.encode(
            payload,
            signer.private,
            algorithm=signer.alg,
            headers={"kid": signer.kid, **(headers or {})},
        )

    def auth(self, user_id: UUID) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.mint(user_id)}"}


def make_verifier(
    jwks: FakeJwks, *, clock: Callable[[], float] = time.monotonic, leeway_s: int = 30
) -> TokenVerifier:
    cache = JwksCache(jwks, ttl_s=600, min_refresh_interval_s=30, clock=clock)
    return TokenVerifier(cache, issuer=ISSUER, leeway_s=leeway_s)


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "environment": "local",
        "supabase_url": SUPABASE_URL,
        "web_origin": (WEB_ORIGIN,),
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


class ScriptedAgent:
    """Yields the given events; answers "Hello there." with usage when given none."""

    def __init__(self, events: list[AgentEvent] | None = None) -> None:
        self.events = events
        self.requests: list[AgentRequest] = []

    async def answer(self, request: AgentRequest) -> AsyncIterator[AgentEvent]:
        self.requests.append(request)
        default: list[AgentEvent] = [
            TextEvent(text="Hello "),
            TextEvent(text="there."),
            AgentUsage(model="fake/model", input_tokens=12, output_tokens=3),
        ]
        for event in default if self.events is None else self.events:
            yield event


@dataclass
class Harness:
    """An app on in-memory storage and limits, a client, and a signed-in user."""

    app: FastAPI
    client: TestClient
    tokens: Tokens
    store: InMemoryChatStore
    limiter: InMemoryRateLimiter
    user_id: UUID = field(default_factory=uuid4)

    @property
    def headers(self) -> dict[str, str]:
        return self.tokens.auth(self.user_id)

    def create_chat(self, title: str = "Ramp") -> UUID:
        response = self.client.post("/v1/chats", json={"title": title}, headers=self.headers)
        response.raise_for_status()
        return UUID(response.json()["id"])


def make_harness(
    tokens: Tokens,
    jwks: FakeJwks,
    *,
    agent: Agent | None = None,
    settings: Settings | None = None,
) -> Harness:
    """`agent=None` leaves the real provider in place, which answers 501 until D9."""
    resolved = settings or make_settings()
    services = Services(settings=resolved, verifier=make_verifier(jwks), database=Database(None))
    app = create_app(services=services)
    store = InMemoryChatStore()
    limiter = InMemoryRateLimiter(
        messages_per_hour=resolved.messages_per_hour,
        concurrent_streams=resolved.concurrent_streams,
        lease_s=resolved.stream_lease_s,
    )
    app.dependency_overrides[get_chat_repo] = lambda: InMemoryChatRepository(store)
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    if agent is not None:
        app.dependency_overrides[get_agent] = lambda: agent
    client = TestClient(app, raise_server_exceptions=False)
    return Harness(app, client, tokens, store, limiter)
