"""The port every model adapter implements, and a helper that collects a whole turn."""

from collections.abc import AsyncIterator
from typing import Protocol

from cardwise_llm.errors import ErrorKind, LLMError
from cardwise_llm.types import (
    Finished,
    FinishReason,
    LLMEvent,
    LLMRequest,
    LLMResponse,
    TextDelta,
    ToolCall,
    ToolCallReady,
    Usage,
    UsageReport,
)


class ChatModel(Protocol):
    """One model turn: request in, events out.

    Implementations yield zero or more TextDelta, ToolCallReady and UsageReport events and end
    with exactly one Finished. Failures raise LLMError, never a provider exception.
    """

    @property
    def name(self) -> str:
        """`provider:model`, used in logs and usage records."""
        ...

    def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]: ...


async def complete(model: ChatModel, request: LLMRequest) -> LLMResponse:
    text: list[str] = []
    calls: list[ToolCall] = []
    usage = Usage()
    reported = False
    reason: FinishReason | None = None

    async for event in model.stream(request):
        if reason is not None:
            raise LLMError(ErrorKind.PROVIDER_DOWN, "event after finish", model=model.name)
        match event:
            case TextDelta():
                text.append(event.text)
            case ToolCallReady():
                calls.append(event.call)
            case UsageReport():
                usage += event.usage
                reported = True
            case Finished():
                reason = event.reason

    if reason is None:
        raise LLMError(ErrorKind.PROVIDER_DOWN, "stream ended without finish", model=model.name)
    if not reported:
        usage = usage.model_copy(update={"unmeasured": True})
    return LLMResponse(
        model=model.name,
        text="".join(text),
        tool_calls=tuple(calls),
        usage=usage,
        finish_reason=reason,
    )
