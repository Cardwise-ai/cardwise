from uuid import UUID, uuid4

import pytest

from cardwise_api.testing import Harness


def test_create_list_get_rename_delete(harness: Harness) -> None:
    client, headers = harness.client, harness.headers
    created = client.post("/v1/chats", json={}, headers=headers)
    assert created.status_code == 201
    chat = created.json()
    assert chat["title"] == "New chat"

    assert client.get(f"/v1/chats/{chat['id']}", headers=headers).json() == chat
    listed = client.get("/v1/chats", headers=headers).json()
    assert listed == {"items": [chat], "next_cursor": None}

    renamed = client.patch(f"/v1/chats/{chat['id']}", json={"title": "  Elves  "}, headers=headers)
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Elves"
    assert renamed.json()["updated_at"] > chat["updated_at"]

    deleted = client.delete(f"/v1/chats/{chat['id']}", headers=headers)
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert client.get(f"/v1/chats/{chat['id']}", headers=headers).status_code == 404
    assert client.get("/v1/chats", headers=headers).json()["items"] == []


def test_other_users_chats_look_missing(harness: Harness) -> None:
    chat_id = harness.create_chat()
    stranger = harness.tokens.auth(uuid4())
    client = harness.client
    for response in (
        client.get(f"/v1/chats/{chat_id}", headers=stranger),
        client.patch(f"/v1/chats/{chat_id}", json={"title": "mine"}, headers=stranger),
        client.delete(f"/v1/chats/{chat_id}", headers=stranger),
        client.get(f"/v1/chats/{chat_id}/messages", headers=stranger),
        client.post(f"/v1/chats/{chat_id}/messages", json={"content": "hi"}, headers=stranger),
    ):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
    assert client.get("/v1/chats", headers=stranger).json()["items"] == []
    assert client.get(f"/v1/chats/{chat_id}", headers=harness.headers).json()["title"] == "Ramp"


def test_chats_page_by_recent_activity(harness: Harness) -> None:
    ids = [harness.create_chat(f"chat {i}") for i in range(5)]
    seen: list[UUID] = []
    cursor = None
    while True:
        params: dict[str, str | int] = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        page = harness.client.get("/v1/chats", params=params, headers=harness.headers).json()
        seen += [UUID(c["id"]) for c in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == list(reversed(ids))


def test_messages_page_oldest_first(harness: Harness) -> None:
    chat_id = harness.create_chat()
    for text in ("one", "two"):
        response = harness.client.post(
            f"/v1/chats/{chat_id}/messages", json={"content": text}, headers=harness.headers
        )
        assert response.status_code == 200
    url = f"/v1/chats/{chat_id}/messages"
    first = harness.client.get(url, params={"limit": 3}, headers=harness.headers).json()
    assert [(m["role"], m["content"]) for m in first["items"]] == [
        ("user", "one"),
        ("assistant", "Hello there."),
        ("user", "two"),
    ]
    rest = harness.client.get(
        url, params={"cursor": first["next_cursor"]}, headers=harness.headers
    ).json()
    assert [m["content"] for m in rest["items"]] == ["Hello there."]
    assert rest["next_cursor"] is None


@pytest.mark.parametrize("cursor", ["garbage!", "bm90LWEtZGF0ZXxub3QtYS11dWlk", "x" * 201])
def test_bad_cursors_are_422(harness: Harness, cursor: str) -> None:
    response = harness.client.get("/v1/chats", params={"cursor": cursor}, headers=harness.headers)
    assert response.status_code == 422
    assert response.json()["error"]["fields"] == ["cursor"]


def test_chat_bodies_are_strict(harness: Harness) -> None:
    client, headers = harness.client, harness.headers
    assert client.post("/v1/chats", json={"title": ""}, headers=headers).status_code == 422
    assert client.post("/v1/chats", json={"title": "x" * 121}, headers=headers).status_code == 422
    smuggled = client.post("/v1/chats", json={"user_id": str(uuid4())}, headers=headers)
    assert smuggled.status_code == 422
    assert client.get("/v1/chats/not-a-uuid", headers=headers).status_code == 422
