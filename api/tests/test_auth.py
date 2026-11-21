import time
from typing import Any
from uuid import uuid4

import jwt
import pytest

from cardwise_api.auth import AuthenticationError, JwksCache, JwksUnavailableError, TokenVerifier
from cardwise_api.testing import (
    ISSUER,
    FakeJwks,
    Harness,
    Tokens,
    ec_key,
    make_verifier,
    rsa_key,
)


async def test_valid_token_gives_the_subject(jwks: FakeJwks, tokens: Tokens) -> None:
    user_id = uuid4()
    user = await make_verifier(jwks).verify(tokens.mint(user_id))
    assert user.id == user_id


async def test_rs256_keys_work(tokens: Tokens) -> None:
    key = rsa_key()
    verifier = make_verifier(FakeJwks([key]))
    user_id = uuid4()
    assert (await verifier.verify(tokens.mint(user_id, key=key))).id == user_id


@pytest.mark.parametrize(
    "claims",
    [
        {"exp": int(time.time()) - 120},
        {"nbf": int(time.time()) + 120},
        {"aud": "anon"},
        {"iss": "https://other-project.supabase.co/auth/v1"},
        {"sub": "service_role"},
        {"is_anonymous": True},
        {"exp": None},
        {"iat": None},
    ],
    ids=["expired", "not-yet-valid", "audience", "issuer", "sub", "anonymous", "no-exp", "no-iat"],
)
async def test_bad_claims_are_rejected(
    jwks: FakeJwks, tokens: Tokens, claims: dict[str, Any]
) -> None:
    with pytest.raises(AuthenticationError):
        await make_verifier(jwks).verify(tokens.mint(**claims))


async def test_small_clock_skew_is_tolerated(jwks: FakeJwks, tokens: Tokens) -> None:
    token = tokens.mint(exp=int(time.time()) - 5)
    assert await make_verifier(jwks, leeway_s=30).verify(token)


async def test_symmetric_and_unsigned_tokens_are_rejected(jwks: FakeJwks) -> None:
    claims = {"sub": str(uuid4()), "iss": ISSUER, "aud": "authenticated", "exp": 2**31}
    hs256 = jwt.encode(claims, "x" * 32, algorithm="HS256", headers={"kid": "ec-1"})
    unsigned = jwt.encode(
        claims,
        None,  # type: ignore[arg-type]
        algorithm="none",
        headers={"kid": "ec-1"},
    )
    for token in (hs256, unsigned, "not-a-jwt", "x" * 9000):
        with pytest.raises(AuthenticationError):
            await make_verifier(jwks).verify(token)


async def test_header_alg_must_match_the_key(jwks: FakeJwks, tokens: Tokens) -> None:
    # Signed with RSA but naming the EC key ID: the key decides the algorithm.
    rsa = rsa_key(kid=tokens.key.kid)
    with pytest.raises(AuthenticationError):
        await make_verifier(jwks).verify(tokens.mint(key=rsa))


async def test_signature_from_another_key_is_rejected(jwks: FakeJwks, tokens: Tokens) -> None:
    impostor = ec_key(kid=tokens.key.kid)
    with pytest.raises(AuthenticationError):
        await make_verifier(jwks).verify(tokens.mint(key=impostor))


async def test_rotated_key_is_fetched_once_then_throttled(jwks: FakeJwks, tokens: Tokens) -> None:
    now = [1000.0]
    verifier = make_verifier(jwks, clock=lambda: now[0])
    await verifier.verify(tokens.mint())
    assert jwks.fetches == 1

    rotated = ec_key(kid="ec-2")
    jwks.keys.append(rotated)
    now[0] += 31
    await verifier.verify(tokens.mint(key=rotated))
    assert jwks.fetches == 2

    # Unknown key IDs within the refresh interval don't trigger more fetches.
    stranger = ec_key(kid="ec-unknown")
    for _ in range(5):
        with pytest.raises(AuthenticationError):
            await verifier.verify(tokens.mint(key=stranger))
    assert jwks.fetches == 2


async def test_cached_keys_survive_a_failed_refresh(tokens: Tokens) -> None:
    calls = 0
    now = [0.0]

    async def flaky() -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls > 1:
            raise JwksUnavailableError("down")
        return {"keys": [tokens.key.jwk]}

    cache = JwksCache(flaky, ttl_s=60, min_refresh_interval_s=0, clock=lambda: now[0])
    verifier = TokenVerifier(cache, issuer=ISSUER)
    await verifier.verify(tokens.mint())
    now[0] = 120
    await verifier.verify(tokens.mint())
    assert calls == 2


async def test_no_keys_at_all_is_unavailable(tokens: Tokens) -> None:
    async def down() -> dict[str, object]:
        raise JwksUnavailableError("down")

    verifier = TokenVerifier(JwksCache(down), issuer=ISSUER)
    with pytest.raises(JwksUnavailableError):
        await verifier.verify(tokens.mint())


def test_routes_answer_401_with_a_bearer_challenge(harness: Harness) -> None:
    for headers in (
        {},
        {"Authorization": "Bearer nonsense"},
        {"Authorization": f"Basic {harness.tokens.mint()}"},
        {"Authorization": f"Bearer {harness.tokens.mint(aud='anon')}"},
    ):
        response = harness.client.get("/v1/chats", headers=headers)
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
        assert response.json()["error"]["code"] == "unauthorized"
