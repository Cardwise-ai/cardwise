"""Contract suite: every adapter and FakeChatModel behave the same on the same provider replies."""

import json
import logging
from collections.abc import AsyncIterator, Callable

import httpx2
import pytest

from cardwise_llm import (
    ChatModel,
    ErrorKind,
    Finished,
    LLMError,
    LLMEvent,
    LLMRequest,
    Message,
    TextDelta,
    ToolCall,
    ToolSpec,
    UsageReport,
    complete,
)

MakeModel = Callable[[str], ChatModel]
HTTP = ["gemini", "openrouter", "openai_compat"]

SEARCH = ToolSpec(
    name="search_cards",
    description="Search the card corpus.",
    parameters={
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
)
PROMPT = "cards like Craterhoof Behemoth"
REQUEST = LLMRequest(
    messages=(Message.system("You suggest Magic cards."), Message.user(PROMPT)),
    tools=(SEARCH,),
    max_output_tokens=256,
    temperature=0.2,
    timeout_s=10,
)


async def test_text_turn_streams_deltas_usage_and_finish(make_model: MakeModel) -> None:
    model = make_model("text")
    events = [event async for event in model.stream(REQUEST)]

    texts = [event.text for event in events if isinstance(event, TextDelta)]
    assert "".join(texts) == "Hello world"
    assert len(texts) >= 2, "text must stream, not arrive in one piece"
    assert isinstance(events[-1], Finished)
    assert events[-1].reason == "stop"
    usage = [event for event in events if isinstance(event, UsageReport)]
    assert len(usage) == 1
    assert usage[0].usage.input_tokens == 12
    assert usage[0].usage.output_tokens == 3


async def test_tool_turn_emits_whole_tool_calls(make_model: MakeModel) -> None:
    response = await complete(make_model("tool"), REQUEST)

    assert response.finish_reason == "tool_calls"
    assert len(response.tool_calls) == 1
    call = response.tool_calls[0]
    assert call.name == "search_cards"
    assert call.arguments == {"text": "overrun"}
    assert call.id


async def test_length_finish_is_reported(make_model: MakeModel) -> None:
    response = await complete(make_model("length"), REQUEST)
    assert response.finish_reason == "length"
    assert response.text == "Hel"


@pytest.mark.parametrize(
    ("scenario", "kind"),
    [
        ("bad_tool", ErrorKind.BAD_TOOL_CALL),
        ("rate_limit", ErrorKind.RATE_LIMIT),
        ("quota", ErrorKind.QUOTA_EXHAUSTED),
        ("auth", ErrorKind.AUTH),
        ("context", ErrorKind.CONTEXT_TOO_LONG),
        ("down", ErrorKind.PROVIDER_DOWN),
        ("timeout", ErrorKind.TIMEOUT),
    ],
)
async def test_provider_failures_map_to_error_kinds(
    make_model: MakeModel, scenario: str, kind: ErrorKind
) -> None:
    model = make_model(scenario)
    with pytest.raises(LLMError) as raised:
        await complete(model, REQUEST)
    assert raised.value.kind is kind
    assert raised.value.model == model.name or raised.value.model == "fake:scripted"


async def test_rate_limit_carries_retry_after(make_model: MakeModel) -> None:
    with pytest.raises(LLMError) as raised:
        await complete(make_model("rate_limit"), REQUEST)
    assert raised.value.retry_after_s == pytest.approx(7)


async def test_failure_after_text_surfaces_as_provider_down(make_model: MakeModel) -> None:
    seen: list[str] = []
    with pytest.raises(LLMError) as raised:
        await collect_text(make_model("mid_stream").stream(REQUEST), seen)
    assert "".join(seen) == "Hel"
    assert raised.value.kind is ErrorKind.PROVIDER_DOWN


async def collect_text(events: AsyncIterator[LLMEvent], seen: list[str]) -> None:
    async for event in events:
        if isinstance(event, TextDelta):
            seen.append(event.text)


async def test_consumer_can_stop_early(make_model: MakeModel) -> None:
    stream = make_model("text").stream(REQUEST)
    first = await anext(aiter(stream))
    assert isinstance(first, TextDelta)
    aclose = getattr(stream, "aclose", None)
    assert aclose is not None
    await aclose()


async def test_logs_never_contain_prompts_or_keys(
    make_model: MakeModel, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    await complete(make_model("text"), REQUEST)
    with pytest.raises(LLMError):
        await complete(make_model("auth"), REQUEST)
    assert PROMPT not in caplog.text
    assert "test-key-not-real" not in caplog.text


# --- request shape, per provider ---------------------------------------------------------

CALL = ToolCall(id="call_1", name="search_cards", arguments={"text": "overrun"})
HISTORY = LLMRequest(
    messages=(
        Message.system("You suggest Magic cards."),
        Message.user(PROMPT),
        Message.assistant("Searching.", tool_calls=(CALL,)),
        Message.tool_result("call_1", '[{"name": "Overrun"}]'),
    ),
    tools=(SEARCH,),
    max_output_tokens=256,
    temperature=0.2,
)


def _body(request: httpx2.Request) -> dict[str, object]:
    body = json.loads(request.content)
    assert isinstance(body, dict)
    return body


@pytest.mark.parametrize("kit_name", ["gemini"])
async def test_gemini_request_shape(make_model: MakeModel, sent: list[httpx2.Request]) -> None:
    await complete(make_model("text"), HISTORY)

    (request,) = sent
    assert request.url.path.endswith("/models/gemini-test:streamGenerateContent")
    assert request.headers["x-goog-api-key"] == "test-key-not-real"
    body = _body(request)
    assert body["systemInstruction"] == {
        "parts": [{"text": "You suggest Magic cards."}],
        "role": "user",
    }
    contents = body["contents"]
    assert isinstance(contents, list)
    assert [content["role"] for content in contents] == ["user", "model", "user"]
    model_parts = contents[1]["parts"]
    assert {"text": "Searching."} in model_parts
    calls = [part["functionCall"] for part in model_parts if "functionCall" in part]
    assert calls[0]["name"] == "search_cards"
    assert calls[0]["args"] == {"text": "overrun"}
    returns = [part["functionResponse"] for part in contents[2]["parts"]]
    assert returns[0]["name"] == "search_cards"
    tools = body["tools"]
    assert isinstance(tools, list)
    assert tools[0]["functionDeclarations"][0]["name"] == "search_cards"
    config = body["generationConfig"]
    assert isinstance(config, dict)
    assert config["maxOutputTokens"] == 256
    assert config["temperature"] == pytest.approx(0.2)


@pytest.mark.parametrize("kit_name", ["openrouter", "openai_compat"])
async def test_openai_request_shape(make_model: MakeModel, sent: list[httpx2.Request]) -> None:
    await complete(make_model("text"), HISTORY)

    (request,) = sent
    assert request.url.path.endswith("/chat/completions")
    assert request.headers["authorization"] == "Bearer test-key-not-real"
    body = _body(request)
    assert body["stream"] is True
    messages = body["messages"]
    assert isinstance(messages, list)
    assert [message["role"] for message in messages] == ["system", "user", "assistant", "tool"]
    tool_call = messages[2]["tool_calls"][0]
    assert tool_call["id"] == "call_1"
    assert tool_call["function"]["name"] == "search_cards"
    assert json.loads(tool_call["function"]["arguments"]) == {"text": "overrun"}
    assert messages[3]["tool_call_id"] == "call_1"
    tools = body["tools"]
    assert isinstance(tools, list)
    assert tools[0]["function"]["name"] == "search_cards"
    assert body.get("max_tokens", body.get("max_completion_tokens")) == 256
    assert body["temperature"] == pytest.approx(0.2)


@pytest.mark.parametrize("kit_name", HTTP)
async def test_tool_result_without_its_call_is_rejected(make_model: MakeModel) -> None:
    orphan = LLMRequest(messages=(Message.user(PROMPT), Message.tool_result("nope", "[]")))
    with pytest.raises(LLMError) as raised:
        await complete(make_model("text"), orphan)
    assert raised.value.kind is ErrorKind.BAD_REQUEST
