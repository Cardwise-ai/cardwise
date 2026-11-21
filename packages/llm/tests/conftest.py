"""Recorded-shape HTTP fixtures for the adapter contract suite. No test here touches the network.

`make_model(scenario)` builds the adapter under test (or a FakeChatModel) wired to a mock transport
that answers every request with that scenario's response, shaped like the provider's real one.
"""

import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx2
import pytest

from cardwise_llm import (
    ChatModel,
    ErrorKind,
    FakeChatModel,
    FakeTurn,
    Finished,
    LLMError,
    TextDelta,
    ToolCall,
    Usage,
    UsageReport,
)
from cardwise_llm.adapters.openai_compat import OpenAICompatAdapter
from cardwise_llm.adapters.pydantic_ai_adapter import gemini, openrouter

API_KEY = "test-key-not-real"
Scenario = str
Reply = httpx2.Response | Exception

HTTP_KITS = ("gemini", "openrouter", "openai_compat")
ALL_KITS = (*HTTP_KITS, "fake")


def _sse(*events: object) -> bytes:
    return "".join(
        f"data: {event if isinstance(event, str) else json.dumps(event)}\n\n" for event in events
    ).encode()


def _stream(body: bytes) -> httpx2.Response:
    return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=body)


def _json(status: int, body: object, headers: dict[str, str] | None = None) -> httpx2.Response:
    return httpx2.Response(status, json=body, headers=headers)


class _Broken(httpx2.AsyncByteStream):
    """A response body that delivers its first chunk, then the connection drops."""

    def __init__(self, first: bytes) -> None:
        self._first = first

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield self._first
        raise httpx2.RemoteProtocolError("peer closed connection without sending complete message")


def _broken(first: bytes) -> httpx2.Response:
    return httpx2.Response(
        200, headers={"content-type": "text/event-stream"}, stream=_Broken(first)
    )


# --- Gemini (generativelanguage.googleapis.com, streamGenerateContent?alt=sse) ---------------


def _gemini_chunk(parts: list[dict[str, Any]], *, finish: str | None, out: int) -> dict[str, Any]:
    candidate: dict[str, Any] = {"content": {"parts": parts, "role": "model"}, "index": 0}
    if finish:
        candidate["finishReason"] = finish
    return {
        "candidates": [candidate],
        "usageMetadata": {
            "promptTokenCount": 12,
            "candidatesTokenCount": out,
            "totalTokenCount": 12 + out,
        },
        "modelVersion": "gemini-test",
        "responseId": "resp-1",
    }


def _gemini_error(code: int, status: str, message: str, *details: object) -> httpx2.Response:
    return _json(
        code,
        {"error": {"code": code, "message": message, "status": status, "details": list(details)}},
    )


_FREE_TIER_METRIC = "generativelanguage.googleapis.com/generate_content_free_tier_requests"


def _gemini_quota(quota_id: str) -> httpx2.Response:
    return _gemini_error(
        429,
        "RESOURCE_EXHAUSTED",
        "You exceeded your current quota, please check your plan and billing details.",
        {
            "@type": "type.googleapis.com/google.rpc.QuotaFailure",
            "violations": [
                {
                    "quotaMetric": _FREE_TIER_METRIC,
                    "quotaId": quota_id,
                    "quotaDimensions": {"location": "global", "model": "gemini-test"},
                    "quotaValue": "20",
                }
            ],
        },
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "7s"},
    )


def gemini_reply(scenario: Scenario, request: httpx2.Request) -> Reply:
    call = {"functionCall": {"name": "search_cards", "args": {"text": "overrun"}}}
    match scenario:
        case "text":
            return _stream(
                _sse(
                    _gemini_chunk([{"text": "Hello"}], finish=None, out=1),
                    _gemini_chunk([{"text": " world"}], finish="STOP", out=3),
                )
            )
        case "tool":
            return _stream(_sse(_gemini_chunk([call], finish="STOP", out=3)))
        case "bad_tool":
            bad = {"functionCall": {"name": "Search Cards!", "args": {"text": "overrun"}}}
            return _stream(_sse(_gemini_chunk([bad], finish="STOP", out=3)))
        case "length":
            return _stream(_sse(_gemini_chunk([{"text": "Hel"}], finish="MAX_TOKENS", out=3)))
        case "rate_limit":
            return _gemini_quota("GenerateRequestsPerMinutePerProjectPerModel-FreeTier")
        case "quota":
            return _gemini_quota("GenerateRequestsPerDayPerProjectPerModel-FreeTier")
        case "auth":
            return _gemini_error(
                400,
                "INVALID_ARGUMENT",
                "API key not valid. Please pass a valid API key.",
                {
                    "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                    "reason": "API_KEY_INVALID",
                    "domain": "googleapis.com",
                },
            )
        case "context":
            return _gemini_error(
                400,
                "INVALID_ARGUMENT",
                "The input token count (2000000) exceeds the maximum number of tokens allowed "
                "(1048576).",
            )
        case "down":
            return _gemini_error(
                503, "UNAVAILABLE", "The model is overloaded. Please try again later."
            )
        case "timeout":
            return httpx2.ReadTimeout("timed out", request=request)
        case "mid_stream":
            return _broken(_sse(_gemini_chunk([{"text": "Hel"}], finish=None, out=1)))
    raise AssertionError(scenario)


# --- OpenAI chat completions (OpenRouter and any OpenAI-compatible endpoint) ----------------


def _chunk(delta: dict[str, Any] | None, finish: str | None = None, **extra: Any) -> dict[str, Any]:
    choices = [] if delta is None else [{"index": 0, "delta": delta, "finish_reason": finish}]
    return {
        "id": "gen-1",
        "object": "chat.completion.chunk",
        "created": 1_763_700_000,
        "model": "vendor/test-model",
        "choices": choices,
        **extra,
    }


_USAGE = {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15}


def _openai_error(
    status: int, message: str, code: object = None, **headers: str
) -> httpx2.Response:
    return _json(
        status,
        {"error": {"message": message, "code": status if code is None else code}},
        headers=headers or None,
    )


def openai_reply(scenario: Scenario, request: httpx2.Request) -> Reply:
    match scenario:
        case "text":
            return _stream(
                _sse(
                    _chunk({"role": "assistant", "content": "Hello"}),
                    _chunk({"content": " world"}, "stop"),
                    _chunk(None, usage=_USAGE),
                    "[DONE]",
                )
            )
        case "tool" | "bad_tool":
            args = '"overrun"}' if scenario == "tool" else "overrun"
            start = {"index": 0, "id": "call_1", "type": "function"}
            return _stream(
                _sse(
                    _chunk(
                        {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {**start, "function": {"name": "search_cards", "arguments": ""}}
                            ],
                        }
                    ),
                    _chunk({"tool_calls": [{"index": 0, "function": {"arguments": '{"text": '}}]}),
                    _chunk({"tool_calls": [{"index": 0, "function": {"arguments": args}}]}),
                    _chunk({}, "tool_calls"),
                    _chunk(None, usage=_USAGE),
                    "[DONE]",
                )
            )
        case "length":
            return _stream(
                _sse(
                    _chunk({"role": "assistant", "content": "Hel"}, "length"),
                    _chunk(None, usage=_USAGE),
                    "[DONE]",
                )
            )
        case "rate_limit":
            return _openai_error(
                429, "Rate limit exceeded: free-models-per-min. ", **{"retry-after": "7"}
            )
        case "quota":
            return _openai_error(
                429,
                "Rate limit exceeded: free-models-per-day. Add 10 credits to unlock 1000 free "
                "model requests per day",
            )
        case "auth":
            return _openai_error(401, "No auth credentials found")
        case "context":
            return _openai_error(
                400,
                "This endpoint's maximum context length is 131072 tokens. However, you requested "
                "about 200000 tokens. Please reduce the length of either one, or use the "
                '"middle-out" transform to compress your prompt automatically.',
            )
        case "down":
            return _openai_error(502, "Provider returned error")
        case "timeout":
            return httpx2.ReadTimeout("timed out", request=request)
        case "mid_stream":
            return _broken(_sse(_chunk({"role": "assistant", "content": "Hel"})))
    raise AssertionError(scenario)


# --- FakeChatModel equivalents ------------------------------------------------------------


def _fake_error(kind: ErrorKind, retry_after_s: float | None = None) -> FakeTurn:
    return [LLMError(kind, "scripted", model="fake:scripted", retry_after_s=retry_after_s)]


def fake_turn(scenario: Scenario) -> FakeTurn:
    call = ToolCall(id="call_1", name="search_cards", arguments={"text": "overrun"})
    turns: dict[str, FakeTurn] = {
        "text": [
            TextDelta(text="Hello"),
            *FakeChatModel.text_turn(" world", usage=Usage(input_tokens=12, output_tokens=3)),
        ],
        "tool": FakeChatModel.tool_turn(call),
        "bad_tool": _fake_error(ErrorKind.BAD_TOOL_CALL),
        "length": [
            TextDelta(text="Hel"),
            UsageReport(usage=Usage(input_tokens=12, output_tokens=3), model="fake:scripted"),
            Finished(reason="length"),
        ],
        "rate_limit": _fake_error(ErrorKind.RATE_LIMIT, 7),
        "quota": _fake_error(ErrorKind.QUOTA_EXHAUSTED),
        "auth": _fake_error(ErrorKind.AUTH),
        "context": _fake_error(ErrorKind.CONTEXT_TOO_LONG),
        "down": _fake_error(ErrorKind.PROVIDER_DOWN),
        "timeout": _fake_error(ErrorKind.TIMEOUT),
        "mid_stream": [
            TextDelta(text="Hel"),
            LLMError(ErrorKind.PROVIDER_DOWN, "dropped", model="fake:scripted"),
        ],
    }
    return turns[scenario]


# --- fixtures -------------------------------------------------------------------------------


@pytest.fixture(params=ALL_KITS)
def kit_name(request: pytest.FixtureRequest) -> str:
    return str(request.param)


@pytest.fixture
def sent() -> list[httpx2.Request]:
    """Every HTTP request the adapter under test sent, in order."""
    return []


@pytest.fixture
def make_model(kit_name: str, sent: list[httpx2.Request]) -> Callable[[Scenario], ChatModel]:
    def build(scenario: Scenario) -> ChatModel:
        if kit_name == "fake":
            return FakeChatModel([fake_turn(scenario)])
        reply = gemini_reply if kit_name == "gemini" else openai_reply

        async def handle(request: httpx2.Request) -> httpx2.Response:
            await request.aread()
            sent.append(request)
            result = reply(scenario, request)
            if isinstance(result, Exception):
                raise result
            return result

        client = httpx2.AsyncClient(transport=httpx2.MockTransport(handle), timeout=30)
        match kit_name:
            case "gemini":
                return gemini("gemini-test", api_key=API_KEY, http_client=client)
            case "openrouter":
                return openrouter("vendor/test-model:free", api_key=API_KEY, http_client=client)
            case _:
                return OpenAICompatAdapter(
                    "vendor/test-model",
                    base_url="https://llm.example.test/v1",
                    api_key=API_KEY,
                    provider="compat",
                    http_client=client,
                )

    return build
