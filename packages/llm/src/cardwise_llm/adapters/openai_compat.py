"""ChatModel adapter for any OpenAI-compatible chat completions endpoint (the escape hatch).

Talks to the endpoint with the `openai` SDK and a `base_url`, e.g. OpenRouter, Groq or Workers
AI. The SDK's own retries are off (`max_retries=0`); ResilientModel owns retries.
"""

import asyncio
import json
from collections.abc import AsyncIterator, Iterable, Sequence
from dataclasses import dataclass, field

import httpx2
import openai
from openai.types import CompletionUsage
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionChunk,
    ChatCompletionMessageFunctionToolCallParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionToolMessageParam,
    ChatCompletionToolParam,
    ChatCompletionUserMessageParam,
)

from cardwise_llm.adapters._common import (
    logger,
    mentions_daily_cap,
    parse_tool_call,
    tool_name_for,
    tool_names_by_call_id,
    unmapped,
)
from cardwise_llm.errors import ErrorKind, LLMError
from cardwise_llm.types import (
    Finished,
    FinishReason,
    LLMEvent,
    LLMRequest,
    Message,
    Role,
    TextDelta,
    ToolCallReady,
    ToolSpec,
    Usage,
    UsageReport,
)

_FINISH: dict[str, FinishReason] = {
    "stop": "stop",
    "length": "length",
    "tool_calls": "tool_calls",
    "function_call": "tool_calls",
    "content_filter": "filtered",
}


@dataclass
class _PendingCall:
    id: str | None = None
    name: str = ""
    arguments: list[str] = field(default_factory=list[str])


class OpenAICompatAdapter:
    def __init__(
        self,
        model_id: str,
        *,
        base_url: str,
        api_key: str,
        provider: str = "openai_compat",
        http_client: httpx2.AsyncClient | None = None,
        max_timeout_s: float | None = None,
    ) -> None:
        self._model_id = model_id
        self._max_timeout_s = max_timeout_s
        self._name = f"{provider}:{model_id}"
        self._client = openai.AsyncOpenAI(
            api_key=api_key, base_url=base_url, max_retries=0, http_client=http_client
        )

    @property
    def name(self) -> str:
        return self._name

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        loop = asyncio.get_running_loop()
        timeout = min(request.timeout_s, self._max_timeout_s or request.timeout_s)
        deadline = loop.time() + timeout
        calls: dict[int, _PendingCall] = {}
        usage: CompletionUsage | None = None
        finish: str | None = None
        try:
            stream = await asyncio.wait_for(
                self._client.chat.completions.create(
                    model=self._model_id,
                    messages=to_openai_messages(request.messages, model=self._name),
                    tools=to_openai_tools(request.tools) if request.tools else openai.omit,
                    stream=True,
                    stream_options={"include_usage": True},
                    max_tokens=request.max_output_tokens,
                    temperature=request.temperature,
                    timeout=timeout,
                ),
                timeout,
            )
            async with stream:
                chunks = aiter(stream)
                while True:
                    remaining = deadline - loop.time()
                    if remaining <= 0:
                        raise TimeoutError
                    try:
                        chunk = await asyncio.wait_for(anext(chunks), remaining)
                    except StopAsyncIteration:
                        break
                    usage = chunk.usage or usage
                    text, reason = _absorb(chunk, calls)
                    finish = reason or finish
                    if text:
                        yield TextDelta(text=text)
        except LLMError:
            raise
        except Exception as exc:
            raise map_openai_error(exc, model=self._name) from exc

        for index in sorted(calls):
            pending = calls[index]
            yield ToolCallReady(
                call=parse_tool_call(
                    pending.id,
                    pending.name,
                    "".join(pending.arguments),
                    model=self._name,
                    index=index,
                )
            )
        yield UsageReport(usage=_usage(usage), model=self._name)
        yield Finished(reason=self._finish_reason(finish, has_calls=bool(calls)))

    def _finish_reason(self, reason: str | None, *, has_calls: bool) -> FinishReason:
        if reason == "error":
            raise LLMError(
                ErrorKind.PROVIDER_DOWN, "provider ended the turn with an error", model=self._name
            )
        if has_calls:
            return "tool_calls"
        mapped = _FINISH.get(reason or "stop", "stop")
        return "stop" if mapped == "tool_calls" else mapped


def _absorb(chunk: ChatCompletionChunk, calls: dict[int, _PendingCall]) -> tuple[str, str | None]:
    text: list[str] = []
    reason: str | None = None
    for choice in chunk.choices:
        if choice.delta.content:
            text.append(choice.delta.content)
        for delta in choice.delta.tool_calls or ():
            pending = calls.setdefault(delta.index, _PendingCall())
            pending.id = delta.id or pending.id
            if delta.function is not None:
                pending.name += delta.function.name or ""
                pending.arguments.append(delta.function.arguments or "")
        reason = choice.finish_reason or reason
    return "".join(text), reason


def _usage(usage: CompletionUsage | None) -> Usage:
    if usage is None:
        return Usage(unmeasured=True)
    cached = usage.prompt_tokens_details.cached_tokens if usage.prompt_tokens_details else None
    reasoning = (
        usage.completion_tokens_details.reasoning_tokens
        if usage.completion_tokens_details
        else None
    )
    return Usage(
        input_tokens=usage.prompt_tokens,
        output_tokens=usage.completion_tokens,
        cached_tokens=cached or 0,
        reasoning_tokens=reasoning or 0,
    )


def to_openai_messages(
    messages: Sequence[Message], *, model: str
) -> list[ChatCompletionMessageParam]:
    names = tool_names_by_call_id(tuple(messages))
    converted: list[ChatCompletionMessageParam] = []
    for message in messages:
        match message.role:
            case Role.SYSTEM:
                converted.append(
                    ChatCompletionSystemMessageParam(role="system", content=message.content)
                )
            case Role.USER:
                converted.append(
                    ChatCompletionUserMessageParam(role="user", content=message.content)
                )
            case Role.TOOL:
                tool_name_for(message, names, model=model)
                converted.append(
                    ChatCompletionToolMessageParam(
                        role="tool",
                        content=message.content,
                        tool_call_id=message.tool_call_id or "",
                    )
                )
            case Role.ASSISTANT:
                assistant = ChatCompletionAssistantMessageParam(
                    role="assistant", content=message.content or None
                )
                if message.tool_calls:
                    assistant["tool_calls"] = [
                        ChatCompletionMessageFunctionToolCallParam(
                            id=call.id,
                            type="function",
                            function={"name": call.name, "arguments": json.dumps(call.arguments)},
                        )
                        for call in message.tool_calls
                    ]
                converted.append(assistant)
    return converted


def to_openai_tools(tools: Iterable[ToolSpec]) -> list[ChatCompletionToolParam]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": dict(tool.parameters),
            },
        }
        for tool in tools
    ]


def map_openai_error(exc: Exception, *, model: str) -> LLMError:
    if isinstance(exc, TimeoutError | openai.APITimeoutError):
        return LLMError(ErrorKind.TIMEOUT, "request timed out", model=model)
    if isinstance(exc, openai.APIConnectionError):
        return LLMError(ErrorKind.PROVIDER_DOWN, "connection failed", model=model)
    if not isinstance(exc, openai.APIError):
        return unmapped(exc, model=model)

    status = exc.status_code if isinstance(exc, openai.APIStatusError) else _in_stream_status(exc)
    text = f"{exc.code or ''} {exc.message}".lower()
    kind = _kind_of(status, text)
    retry_after = _retry_after(exc) if isinstance(exc, openai.APIStatusError) else None
    detail = " ".join(str(part) for part in ("HTTP", status, exc.code) if part is not None)
    logger.debug("provider error from %s mapped to %s (%s)", model, kind, detail)
    return LLMError(kind, detail, model=model, retry_after_s=retry_after)


def _in_stream_status(exc: openai.APIError) -> int | None:
    """OpenRouter reports mid-stream failures as `{"error": {"code": <http status>, ...}}`."""
    body = exc.body
    code = body.get("code") if isinstance(body, dict) else None
    return code if isinstance(code, int) else None


def _kind_of(status: int | None, text: str) -> ErrorKind:
    if status == 402 or "insufficient_quota" in text:
        return ErrorKind.QUOTA_EXHAUSTED
    if status == 429:
        if mentions_daily_cap(text):
            return ErrorKind.QUOTA_EXHAUSTED
        return ErrorKind.RATE_LIMIT
    if status in (401, 403):
        if "moderation" in text or "flagged" in text:
            return ErrorKind.CONTENT_FILTERED
        return ErrorKind.AUTH
    if status == 408:
        return ErrorKind.TIMEOUT
    if "context_length" in text or "context length" in text or "maximum context" in text:
        return ErrorKind.CONTEXT_TOO_LONG
    if status is not None and 400 <= status < 500:
        return ErrorKind.BAD_REQUEST
    return ErrorKind.PROVIDER_DOWN


def _retry_after(exc: openai.APIStatusError) -> float | None:
    headers = exc.response.headers
    for header, scale in (("retry-after-ms", 1000.0), ("retry-after", 1.0)):
        value = headers.get(header)
        if value is None:
            continue
        try:
            return max(float(value) / scale, 0.0)
        except ValueError:
            continue
    return None
