from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from cardwise_api.export_schemas import OPENAPI_DIR, render
from cardwise_api.models import ChatCreate, MessageCreate
from cardwise_api.stream_events import stream_event_adapter
from cardwise_api.testing import Harness


@pytest.fixture
def client(harness: Harness) -> TestClient:
    return harness.client


@pytest.mark.parametrize("name", ["openapi.json", "stream-events.schema.json"])
def test_contract_files_match_the_code(name: str) -> None:
    committed = (OPENAPI_DIR / name).read_text(encoding="utf-8")
    assert render()[name] == committed, (
        f"{name} is stale. If the change is intended, run: "
        "uv run python -m cardwise_api.export_schemas"
    )


def test_health_needs_no_auth(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert len(response.headers["x-request-id"]) == 32


def test_missing_token_gets_the_error_shape(client: TestClient) -> None:
    response = client.get("/v1/chats")
    assert response.status_code == 401
    error = response.json()["error"]
    assert error["code"] == "unauthorized"
    assert error["request_id"] == response.headers["x-request-id"]


def test_stubs_answer_not_implemented(harness: Harness) -> None:
    response = harness.client.get(f"/v1/cards/{uuid4()}", headers=harness.headers)
    assert response.status_code == 501
    assert response.json()["error"]["code"] == "not_implemented"


def test_validation_errors_name_fields_but_not_values(harness: Harness) -> None:
    secret = "x" * 4001
    response = harness.client.post(
        f"/v1/chats/{uuid4()}/messages", json={"content": secret}, headers=harness.headers
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["fields"] == ["content"]
    assert secret not in response.text


def test_client_request_id_is_not_trusted(client: TestClient) -> None:
    response = client.get("/healthz", headers={"x-request-id": "attacker-chosen"})
    assert response.headers["x-request-id"] != "attacker-chosen"


def test_bodies_trim_and_bound_text() -> None:
    assert MessageCreate(content="  hi  ").content == "hi"
    with pytest.raises(ValidationError):
        MessageCreate(content="   ")
    with pytest.raises(ValidationError):
        ChatCreate.model_validate({"title": "t", "user_id": str(uuid4())})


def test_stream_events_parse_by_type() -> None:
    event = stream_event_adapter.validate_json('{"type":"text","text":"Craterhoof"}')
    assert event.type == "text"
    with pytest.raises(ValidationError):
        stream_event_adapter.validate_json('{"type":"html","html":"<img src=x>"}')
