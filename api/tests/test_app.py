import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import HttpUrl, ValidationError

from cardwise_api.auth import JwksCache, JwksUnavailableError, TokenVerifier
from cardwise_api.db import Database
from cardwise_api.dependencies import Services, get_chat_repo
from cardwise_api.main import create_app
from cardwise_api.settings import Settings
from cardwise_api.testing import ISSUER, WEB_ORIGIN, Harness, make_settings


def test_security_headers_on_every_response(harness: Harness) -> None:
    for response in (
        harness.client.get("/healthz"),
        harness.client.get("/v1/chats"),
        harness.client.get("/v1/chats", headers=harness.headers),
    ):
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert response.headers["cache-control"] == "no-store"
        assert "strict-transport-security" not in response.headers


def test_hsts_when_deployed_or_https(harness: Harness) -> None:
    https = TestClient(harness.app, base_url="https://testserver")
    assert "max-age" in https.get("/healthz").headers["strict-transport-security"]


def test_cors_allows_only_the_configured_origin(harness: Harness) -> None:
    preflight = {
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type",
    }
    ok = harness.client.options("/v1/chats", headers={"Origin": WEB_ORIGIN, **preflight})
    assert ok.status_code == 200
    assert ok.headers["access-control-allow-origin"] == WEB_ORIGIN
    assert "access-control-allow-credentials" not in ok.headers

    evil = harness.client.options(
        "/v1/chats", headers={"Origin": "https://evil.example", **preflight}
    )
    assert "access-control-allow-origin" not in evil.headers

    simple = harness.client.get("/healthz", headers={"Origin": WEB_ORIGIN})
    assert simple.headers["access-control-allow-origin"] == WEB_ORIGIN
    assert "x-request-id" in simple.headers["access-control-expose-headers"]


def test_cors_preview_regex() -> None:
    settings = make_settings(web_origin_regex=r"^https://cardwise-web-[a-z0-9-]+\.vercel\.app$")
    app = create_app(services=Services(settings=settings, verifier=None, database=Database(None)))
    client = TestClient(app)
    preview = "https://cardwise-web-git-feat-x.vercel.app"
    response = client.get("/healthz", headers={"Origin": preview})
    assert response.headers["access-control-allow-origin"] == preview


def test_unknown_routes_and_methods_use_the_error_shape(harness: Harness) -> None:
    missing = harness.client.get("/nope")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"
    wrong_method = harness.client.put("/v1/chats", headers=harness.headers)
    assert wrong_method.status_code == 405
    assert wrong_method.json()["error"]["code"] == "bad_request"


def test_unconfigured_auth_rejects_everyone(harness: Harness) -> None:
    app = create_app(
        services=Services(settings=make_settings(), verifier=None, database=Database(None))
    )
    response = TestClient(app).get("/v1/chats", headers=harness.headers)
    assert response.status_code == 401


def test_jwks_outage_is_a_500_without_details(harness: Harness) -> None:
    async def down() -> dict[str, object]:
        raise JwksUnavailableError("down")

    verifier = TokenVerifier(JwksCache(down), issuer=ISSUER)
    app = create_app(
        services=Services(settings=make_settings(), verifier=verifier, database=Database(None))
    )
    response = TestClient(app).get("/v1/chats", headers=harness.headers)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal"


def test_unhandled_errors_are_500_and_logged_without_message(
    harness: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    # No chat repo override: the real provider fails because no database is configured.
    del harness.app.dependency_overrides[get_chat_repo]
    logging.getLogger("cardwise_api").propagate = True
    try:
        with caplog.at_level(logging.ERROR, logger="cardwise_api"):
            response = harness.client.get("/v1/chats", headers=harness.headers)
    finally:
        logging.getLogger("cardwise_api").propagate = False
    assert response.status_code == 500
    body = response.json()["error"]
    assert body == {
        "code": "internal",
        "message": "Something went wrong on our side.",
        "request_id": response.headers["x-request-id"],
        "fields": [],
    }
    assert "CARDWISE_DATABASE_URL" not in response.text


def test_access_log_uses_full_route_template_without_ids(
    harness: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    chat_id = str(harness.create_chat())
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="cardwise_api.access"):
        harness.client.get(f"/v1/chats/{chat_id}/messages", headers=harness.headers)
        harness.client.get("/nope")
    routes = [
        r.__dict__["fields"]["route"] for r in caplog.records if r.name == "cardwise_api.access"
    ]
    assert routes == ["/v1/chats/{chat_id}/messages", "unmatched"]
    assert chat_id not in caplog.text


def test_openapi_is_hidden_when_deployed() -> None:
    settings = make_settings(
        environment="production", database_url="postgresql://u:p@db.invalid:6543/postgres"
    )
    app = create_app(services=Services(settings=settings, verifier=None, database=Database(None)))
    assert TestClient(app).get("/openapi.json").status_code == 404


def test_deployed_settings_need_database_and_supabase() -> None:
    with pytest.raises(ValidationError, match="CARDWISE_DATABASE_URL"):
        Settings(
            _env_file=None, environment="preview", supabase_url=HttpUrl("https://x.supabase.co")
        )


@pytest.mark.parametrize(
    "origin", ["*", "https://cardwise.example/", "cardwise.example", "https://*.vercel.app"]
)
def test_web_origin_must_be_an_exact_origin(origin: str) -> None:
    with pytest.raises(ValidationError):
        make_settings(web_origin=origin)


def test_web_origin_is_comma_separated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CARDWISE_WEB_ORIGIN", "https://a.example, https://b.example")
    monkeypatch.setenv("VERCEL_ENV", "development")
    settings = Settings(_env_file=None)
    assert settings.web_origin == ("https://a.example", "https://b.example")
    assert settings.environment == "development"
