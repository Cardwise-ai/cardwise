import asyncio
import json
from collections.abc import AsyncIterator, Callable
from contextlib import suppress
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from starlette.requests import ClientDisconnect
from starlette.types import Message

from cardwise_api.agent.port import AgentEvent, AgentRequest, AgentUsage
from cardwise_api.models import CardRef
from cardwise_api.stream_events import CardsEvent, StartEvent, TextEvent, ToolEvent
from cardwise_api.streaming import HEARTBEAT, encode_event, sse_body
from cardwise_api.testing import Harness, ScriptedAgent, make_settings
from cardwise_llm import ErrorKind, LLMError

HarnessFactory = Callable[..., Harness]


def events_of(response: httpx.Response) -> list[dict[str, Any]]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in response.text.split("\n")
        if line.startswith("data: ")
    ]


def send(harness: Harness, chat_id: UUID, content: str = "Best green ramp?") -> httpx.Response:
    response: httpx.Response = harness.client.post(
        f"/v1/chats/{chat_id}/messages", json={"content": content}, headers=harness.headers
    )
    return response


def stored(harness: Harness, chat_id: UUID) -> list[Any]:
    return [m.message for m in harness.store.messages if m.chat_id == chat_id]


def test_streams_the_answer_and_saves_both_messages(harness: Harness) -> None:
    chat_id = harness.create_chat()
    response = send(harness, chat_id)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no"
    assert "no-cache" in response.headers["cache-control"]
    events = events_of(response)
    assert [e["type"] for e in events] == ["start", "text", "text", "done"]
    assert events[-1] == {
        "type": "done",
        "message_id": events[0]["message_id"],
        "usage": {"input_tokens": 12, "output_tokens": 3},
    }

    user, assistant = stored(harness, chat_id)
    assert (user.role, user.content) == ("user", "Best green ramp?")
    assert (assistant.role, assistant.content, assistant.status) == (
        "assistant",
        "Hello there.",
        "complete",
    )
    assert str(assistant.id) == events[0]["message_id"]
    assert harness.limiter.leases[f"user:{harness.user_id}"] == []


def test_cards_and_tools_are_forwarded_and_saved(new_harness: HarnessFactory) -> None:
    card = CardRef(oracle_id=uuid4(), name="Llanowar Elves", image_uri=None)
    harness = new_harness(
        agent=ScriptedAgent(
            [
                ToolEvent(name="search_cards", status="running"),
                ToolEvent(name="search_cards", status="done"),
                TextEvent(text="Try [[Llanowar Elves]]."),
                CardsEvent(cards=[card, card]),
            ]
        )
    )
    chat_id = harness.create_chat()
    events = events_of(send(harness, chat_id))
    assert [e["type"] for e in events] == ["start", "tool", "tool", "text", "cards", "done"]
    assert events[-1]["usage"] == {"input_tokens": 0, "output_tokens": 0}
    assert stored(harness, chat_id)[1].cards == [card]


def test_agent_gets_history_but_not_the_user(new_harness: HarnessFactory) -> None:
    agent = ScriptedAgent()
    harness = new_harness(agent=agent)
    chat_id = harness.create_chat()
    send(harness, chat_id, "first")
    send(harness, chat_id, "second")
    request = agent.requests[-1]
    assert request.question == "second"
    assert request.chat_id == chat_id
    assert [m.content for m in request.history] == ["first", "Hello there."]
    assert str(harness.user_id) not in request.model_dump_json()


def test_model_failure_sends_an_error_event_and_saves_failed(
    new_harness: HarnessFactory,
) -> None:
    class Failing:
        async def answer(self, request: AgentRequest) -> AsyncIterator[AgentEvent]:
            yield TextEvent(text="Partial")
            raise LLMError(ErrorKind.PROVIDER_DOWN, "boom", model="fake/model")

    harness = new_harness(agent=Failing())
    chat_id = harness.create_chat()
    response = send(harness, chat_id)
    events = events_of(response)
    assert [e["type"] for e in events] == ["start", "text", "error"]
    assert events[-1] == {
        "type": "error",
        "code": "model_unavailable",
        "request_id": response.headers["x-request-id"],
    }
    assert "boom" not in response.text
    assistant = stored(harness, chat_id)[1]
    assert (assistant.content, assistant.status) == ("Partial", "failed")
    assert harness.limiter.leases[f"user:{harness.user_id}"] == []


def test_agent_bug_is_an_internal_error_event(new_harness: HarnessFactory) -> None:
    class Buggy:
        async def answer(self, request: AgentRequest) -> AsyncIterator[AgentEvent]:
            yield AgentUsage(model="fake/model")
            raise KeyError("secret detail")

    harness = new_harness(agent=Buggy())
    chat_id = harness.create_chat()
    response = send(harness, chat_id)
    assert events_of(response)[-1]["code"] == "internal"
    assert "secret detail" not in response.text
    assert stored(harness, chat_id)[1].status == "failed"


def test_without_an_agent_it_is_501_and_costs_nothing(new_harness: HarnessFactory) -> None:
    harness = new_harness(agent=None)
    chat_id = harness.create_chat()
    response = send(harness, chat_id)
    assert response.status_code == 501
    assert response.json()["error"]["code"] == "not_implemented"
    assert stored(harness, chat_id) == []
    assert harness.limiter.leases == {}


def test_hourly_message_limit(harness: Harness) -> None:
    chat_id = harness.create_chat()
    for _ in range(20):
        assert send(harness, chat_id).status_code == 200
    limited = send(harness, chat_id, "one more")
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "rate_limited"
    assert 1 <= int(limited.headers["retry-after"]) <= 3600
    assert "one more" not in [m.content for m in stored(harness, chat_id)]
    assert harness.limiter.leases[f"user:{harness.user_id}"] == []

    # Limits are per user.
    other = harness.tokens.auth(uuid4())
    other_chat = harness.client.post("/v1/chats", json={}, headers=other).json()["id"]
    ok = harness.client.post(
        f"/v1/chats/{other_chat}/messages", json={"content": "hi"}, headers=other
    )
    assert ok.status_code == 200


def test_one_stream_at_a_time(harness: Harness) -> None:
    chat_id = harness.create_chat()
    lease = asyncio.run(harness.limiter.acquire_stream(harness.user_id))
    busy = send(harness, chat_id)
    assert busy.status_code == 429
    assert busy.headers["retry-after"] == "5"
    assert stored(harness, chat_id) == []

    asyncio.run(harness.limiter.release_stream(lease))
    assert send(harness, chat_id).status_code == 200


class Hanging:
    """Says one thing, then waits forever, like a model that stalls mid-answer."""

    def __init__(self) -> None:
        self.closed = False

    async def answer(self, request: AgentRequest) -> AsyncIterator[AgentEvent]:
        try:
            yield TextEvent(text="Partial")
            await asyncio.Event().wait()
        finally:
            self.closed = True


def _scope(harness: Harness, chat_id: UUID, body: bytes, spec_version: str) -> dict[str, Any]:
    headers = {**harness.headers, "content-type": "application/json"}
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": spec_version},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": f"/v1/chats/{chat_id}/messages",
        "raw_path": f"/v1/chats/{chat_id}/messages".encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [
            (k.lower().encode(), v.encode())
            for k, v in {**headers, "content-length": str(len(body))}.items()
        ],
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    }


@pytest.mark.parametrize("spec_version", ["2.3", "2.4"])
async def test_client_disconnect_saves_partial_reply_and_frees_the_slot(
    new_harness: HarnessFactory, spec_version: str
) -> None:
    agent = Hanging()
    # On ASGI 2.4 a gone client is only noticed on the next write: here, a heartbeat.
    harness = new_harness(agent=agent, settings=make_settings(heartbeat_s=0.05))
    chat_id = harness.create_chat()
    body = b'{"content": "hello"}'
    got_text = asyncio.Event()
    requested = False
    chunks: list[bytes] = []

    async def receive() -> Message:
        nonlocal requested
        if not requested:
            requested = True
            return {"type": "http.request", "body": body, "more_body": False}
        await got_text.wait()
        return {"type": "http.disconnect"}

    async def send_(message: Message) -> None:
        if message["type"] != "http.response.body":
            return
        chunks.append(message["body"])
        if b'"text"' in message["body"]:
            got_text.set()
        elif got_text.is_set() and spec_version == "2.4":
            raise OSError("client went away")

    with suppress(ClientDisconnect):
        await asyncio.wait_for(
            harness.app(_scope(harness, chat_id, body, spec_version), receive, send_), 5
        )

    assert got_text.is_set()
    assert agent.closed
    assistant = stored(harness, chat_id)[1]
    assert (assistant.content, assistant.status) == ("Partial", "interrupted")
    assert harness.limiter.leases[f"user:{harness.user_id}"] == []


async def test_heartbeats_while_the_source_is_slow() -> None:
    release = asyncio.Event()

    async def slow() -> AsyncIterator[Any]:
        yield StartEvent(message_id=uuid4())
        await release.wait()
        yield TextEvent(text="finally")

    chunks: list[bytes] = []
    async for chunk in sse_body(slow(), heartbeat_s=0.01):
        chunks.append(chunk)
        if chunks.count(HEARTBEAT) == 3:
            release.set()
    assert chunks[0].startswith(b'data: {"type":"start"')
    assert chunks[1:4] == [HEARTBEAT] * 3
    assert chunks[-1] == encode_event(TextEvent(text="finally"))


def test_encoded_events_are_single_data_lines() -> None:
    frame = encode_event(TextEvent(text="line one\nline two"))
    assert frame.endswith(b"\n\n")
    assert frame.count(b"\n") == 2
    assert frame.startswith(b"data: ")
