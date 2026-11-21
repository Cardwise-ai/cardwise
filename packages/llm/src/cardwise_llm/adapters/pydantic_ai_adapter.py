"""ChatModel adapter over Pydantic AI direct model requests (not its Agent).

Pydantic AI already sorts provider failures into categories (rate limit, quota, auth, context
window, ...), translates tool schemas per provider and keeps Gemini's thought-signature rules, so
one adapter serves Gemini and OpenRouter. We ask it for exactly one attempt (`max_retries=0`);
ResilientModel owns retries.
"""

from collections.abc import AsyncIterator, Sequence

import httpx2
from pydantic_ai import exceptions as pai_errors
from pydantic_ai import messages as pai
from pydantic_ai.direct import model_request_stream
from pydantic_ai.models import Model, ModelRequestParameters
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider
from pydantic_ai.settings import ModelSettings
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.usage import RequestUsage

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
    Usage,
    UsageReport,
)

_FINISH: dict[str, FinishReason] = {
    "stop": "stop",
    "length": "length",
    "content_filter": "filtered",
    "tool_call": "tool_calls",
}


class PydanticAIAdapter:
    def __init__(self, model: Model, *, name: str, max_timeout_s: float | None = None) -> None:
        self._model = model
        self._name = name
        self._max_timeout_s = max_timeout_s

    @property
    def name(self) -> str:
        return self._name

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        history = to_pydantic_ai_messages(request.messages, model=self._name)
        params = ModelRequestParameters(
            function_tools=[
                ToolDefinition(
                    name=tool.name,
                    description=tool.description,
                    parameters_json_schema=dict(tool.parameters),
                )
                for tool in request.tools
            ],
            allow_text_output=True,
        )
        timeout = min(request.timeout_s, self._max_timeout_s or request.timeout_s)
        settings = ModelSettings(
            max_tokens=request.max_output_tokens,
            temperature=request.temperature,
            timeout=timeout,
            request_timeout=timeout,
            max_retries=0,
        )
        try:
            async with model_request_stream(
                self._model, history, model_settings=settings, model_request_parameters=params
            ) as response:
                async for event in response:
                    text = _text_of(event)
                    if text:
                        yield TextDelta(text=text)
                final = response.get()
                usage = response.usage
        except LLMError:
            raise
        except Exception as exc:
            raise map_pydantic_ai_error(exc, model=self._name) from exc

        calls = [part for part in final.parts if isinstance(part, pai.ToolCallPart)]
        for index, part in enumerate(calls):
            yield ToolCallReady(
                call=parse_tool_call(
                    part.tool_call_id, part.tool_name, part.args, model=self._name, index=index
                )
            )
        yield UsageReport(usage=_usage(usage), model=self._name)
        yield Finished(reason=self._finish_reason(final.finish_reason, has_calls=bool(calls)))

    def _finish_reason(self, reason: str | None, *, has_calls: bool) -> FinishReason:
        if has_calls:
            return "tool_calls"
        if reason == "error":
            raise LLMError(
                ErrorKind.PROVIDER_DOWN, "provider ended the turn with an error", model=self._name
            )
        mapped = _FINISH.get(reason or "stop", "stop")
        return "stop" if mapped == "tool_calls" else mapped


def _text_of(event: pai.ModelResponseStreamEvent) -> str:
    if isinstance(event, pai.PartStartEvent) and isinstance(event.part, pai.TextPart):
        return event.part.content
    if isinstance(event, pai.PartDeltaEvent) and isinstance(event.delta, pai.TextPartDelta):
        return event.delta.content_delta
    return ""


def _usage(usage: RequestUsage) -> Usage:
    return Usage(
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cached_tokens=usage.cache_read_tokens,
        reasoning_tokens=usage.output_reasoning_tokens,
        unmeasured=usage.unmeasured_requests > 0 or usage.input_tokens + usage.output_tokens == 0,
    )


def to_pydantic_ai_messages(messages: Sequence[Message], *, model: str) -> list[pai.ModelMessage]:
    """Consecutive system, user and tool messages share one ModelRequest; assistants respond."""
    names = tool_names_by_call_id(tuple(messages))
    history: list[pai.ModelMessage] = []
    pending: list[pai.ModelRequestPart] = []
    for message in messages:
        match message.role:
            case Role.SYSTEM:
                pending.append(pai.SystemPromptPart(content=message.content))
            case Role.USER:
                pending.append(pai.UserPromptPart(content=message.content))
            case Role.TOOL:
                pending.append(
                    pai.ToolReturnPart(
                        tool_name=tool_name_for(message, names, model=model),
                        content=message.content,
                        tool_call_id=message.tool_call_id or "",
                    )
                )
            case Role.ASSISTANT:
                if pending:
                    history.append(pai.ModelRequest(parts=pending))
                    pending = []
                parts: list[pai.ModelResponsePart] = []
                if message.content:
                    parts.append(pai.TextPart(content=message.content))
                parts.extend(
                    pai.ToolCallPart(
                        tool_name=call.name, args=dict(call.arguments), tool_call_id=call.id
                    )
                    for call in message.tool_calls
                )
                history.append(pai.ModelResponse(parts=parts))
    if pending:
        history.append(pai.ModelRequest(parts=pending))
    return history


def map_pydantic_ai_error(exc: Exception, *, model: str) -> LLMError:
    kind = _kind_of(exc)
    if kind is None:
        return unmapped(exc, model=model)
    retry_after = exc.retry_after if isinstance(exc, pai_errors.ModelAPIError) else None
    status = getattr(exc, "status_code", None)
    code = getattr(exc, "provider_error_code", None)
    detail = " ".join(str(part) for part in (type(exc).__name__, status, code) if part)
    logger.debug("provider error from %s mapped to %s (%s)", model, kind, detail)
    return LLMError(kind, detail, model=model, retry_after_s=retry_after)


def _kind_of(exc: Exception) -> ErrorKind | None:
    match exc:
        case pai_errors.ModelQuotaExceededError():
            return ErrorKind.QUOTA_EXHAUSTED
        case pai_errors.ModelRateLimitError():
            # OpenRouter reports its free-models-per-day cap as an ordinary 429.
            if mentions_daily_cap(f"{exc.message} {getattr(exc, 'body', '')}"):
                return ErrorKind.QUOTA_EXHAUSTED
            return ErrorKind.RATE_LIMIT
        case pai_errors.ModelRequestTimeout() | pai_errors.ModelTimeoutError():
            return ErrorKind.TIMEOUT
        case pai_errors.ModelAuthenticationError():
            return ErrorKind.AUTH
        case pai_errors.ModelContextWindowExceededError():
            return ErrorKind.CONTEXT_TOO_LONG
        case pai_errors.ModelRequestRejectedError():
            # OpenRouter sends input its moderation flagged as a plain 403 rejection.
            if getattr(exc, "status_code", None) == 403:
                return ErrorKind.CONTENT_FILTERED
            return ErrorKind.BAD_REQUEST
        case (
            pai_errors.ModelUnavailableError()
            | pai_errors.ModelServerError()
            | pai_errors.ModelConnectionError()
        ):
            return ErrorKind.PROVIDER_DOWN
        case pai_errors.ModelHTTPError():
            return _kind_of_status(exc.status_code)
        case pai_errors.ContentFilterError():
            return ErrorKind.CONTENT_FILTERED
        case pai_errors.IncompleteToolCall():
            return ErrorKind.BAD_TOOL_CALL
        case pai_errors.UserError():
            return ErrorKind.BAD_REQUEST
        case pai_errors.ModelAPIError() | pai_errors.UnexpectedModelBehavior():
            return ErrorKind.PROVIDER_DOWN
        case TimeoutError():
            return ErrorKind.TIMEOUT
    return None


def _kind_of_status(status: int) -> ErrorKind:
    if status in (401, 403):
        return ErrorKind.AUTH
    if status == 408:
        return ErrorKind.TIMEOUT
    if status == 429:
        return ErrorKind.RATE_LIMIT
    if 400 <= status < 500:
        return ErrorKind.BAD_REQUEST
    return ErrorKind.PROVIDER_DOWN


def gemini(
    model_id: str,
    *,
    api_key: str,
    http_client: httpx2.AsyncClient | None = None,
    max_timeout_s: float | None = None,
) -> PydanticAIAdapter:
    """Gemini Developer API (Google AI Studio key)."""
    provider = GoogleProvider(api_key=api_key, http_client=http_client)
    return PydanticAIAdapter(
        GoogleModel(model_id, provider=provider),
        name=f"gemini:{model_id}",
        max_timeout_s=max_timeout_s,
    )


def openrouter(
    model_id: str,
    *,
    api_key: str,
    http_client: httpx2.AsyncClient | None = None,
    max_timeout_s: float | None = None,
) -> PydanticAIAdapter:
    """OpenRouter, typically one of its `:free` models."""
    provider = OpenRouterProvider(api_key=api_key, app_title="Cardwise", http_client=http_client)
    return PydanticAIAdapter(
        OpenRouterModel(model_id, provider=provider),
        name=f"openrouter:{model_id}",
        max_timeout_s=max_timeout_s,
    )
