"""Supabase access-token verification against the project's JWKS.

Supabase signs user sessions with an asymmetric key (ES256 by default, RS256 optional) and
publishes the public keys at `<project>/auth/v1/.well-known/jwks.json`. Keys are cached and
refetched when they expire or when a token names a key ID we have not seen (key rotation).
The refetch on an unknown key ID is throttled so forged tokens can't turn into a flood of
JWKS requests.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Final
from uuid import UUID

import httpx
import jwt
from pydantic import BaseModel, ConfigDict

ALLOWED_ALGORITHMS: Final = frozenset({"ES256", "RS256"})
MAX_TOKEN_LENGTH: Final = 8192
REQUIRED_CLAIMS: Final = ["exp", "iat", "iss", "aud", "sub"]

log: Final = logging.getLogger("cardwise_api.auth")

JwksFetcher = Callable[[], Awaitable[Mapping[str, object]]]


class AuthenticatedUser(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    """The token's `sub`: the auth.users ID that owns chats."""


class AuthenticationError(Exception):
    """The token is missing, malformed, expired or not ours. The reason is for logs only."""


class JwksUnavailableError(Exception):
    """The key set could not be fetched and nothing usable is cached."""


def http_jwks_fetcher(url: str, *, timeout_s: float = 5.0) -> JwksFetcher:
    async def fetch() -> Mapping[str, object]:
        async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=False) as client:
            response = await client.get(url, headers={"Accept": "application/json"})
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict):
            raise JwksUnavailableError("JWKS is not a JSON object")
        return data

    return fetch


def _parse_keys(data: Mapping[str, object]) -> dict[str, jwt.PyJWK]:
    keys: dict[str, jwt.PyJWK] = {}
    entries = data.get("keys")
    if not isinstance(entries, list):
        return keys
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        kid, alg = entry.get("kid"), entry.get("alg")
        if not isinstance(kid, str) or alg not in ALLOWED_ALGORITHMS:
            continue
        if entry.get("use", "sig") != "sig":
            continue
        try:
            keys[kid] = jwt.PyJWK(entry, algorithm=str(alg))
        except jwt.PyJWTError:
            log.warning("skipping unusable JWKS key", extra={"fields": {"kid": kid}})
    return keys


class JwksCache:
    def __init__(
        self,
        fetch: JwksFetcher,
        *,
        ttl_s: float = 600,
        min_refresh_interval_s: float = 30,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fetch = fetch
        self._ttl_s = ttl_s
        self._min_refresh_interval_s = min_refresh_interval_s
        self._clock = clock
        self._keys: dict[str, jwt.PyJWK] = {}
        self._fetched_at: float | None = None
        self._lock = asyncio.Lock()

    async def get(self, kid: str) -> jwt.PyJWK | None:
        if self._needs_refresh(kid):
            async with self._lock:
                if self._needs_refresh(kid):
                    await self._refresh()
        return self._keys.get(kid)

    def _needs_refresh(self, kid: str) -> bool:
        if self._fetched_at is None:
            return True
        age = self._clock() - self._fetched_at
        if age >= self._ttl_s:
            return True
        return kid not in self._keys and age >= self._min_refresh_interval_s

    async def _refresh(self) -> None:
        try:
            keys = _parse_keys(await self._fetch())
        except (httpx.HTTPError, ValueError, JwksUnavailableError) as exc:
            self._fetched_at = self._clock()  # back off for the refresh interval either way
            if self._keys:
                log.warning("JWKS refresh failed; keeping cached keys", exc_info=exc)
                return
            raise JwksUnavailableError("could not fetch JWKS") from exc
        self._keys = keys
        self._fetched_at = self._clock()


class TokenVerifier:
    def __init__(
        self, keys: JwksCache, *, issuer: str, audience: str = "authenticated", leeway_s: int = 30
    ) -> None:
        self._keys = keys
        self._issuer = issuer
        self._audience = audience
        self._leeway_s = leeway_s

    async def verify(self, token: str) -> AuthenticatedUser:
        if len(token) > MAX_TOKEN_LENGTH:
            raise AuthenticationError("token too long")
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise AuthenticationError("malformed token") from exc
        alg, kid = header.get("alg"), header.get("kid")
        if alg not in ALLOWED_ALGORITHMS:
            raise AuthenticationError("algorithm not allowed")
        if not isinstance(kid, str):
            raise AuthenticationError("no key id")
        key = await self._keys.get(kid)
        if key is None:
            raise AuthenticationError("unknown key id")
        if key.algorithm_name != alg:
            raise AuthenticationError("algorithm does not match key")
        try:
            claims = jwt.decode(
                token,
                key=key,
                algorithms=[str(alg)],
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._leeway_s,
                options={"require": REQUIRED_CLAIMS},
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationError(type(exc).__name__) from exc
        if claims.get("is_anonymous") is True:
            raise AuthenticationError("anonymous session")
        try:
            user_id = UUID(str(claims["sub"]))
        except ValueError as exc:
            raise AuthenticationError("sub is not a UUID") from exc
        return AuthenticatedUser(id=user_id)
