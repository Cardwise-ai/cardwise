"""A scripted ChatModel for tests and for running the app without API keys."""

from collections.abc import AsyncIterator, Sequence

from cardwise_llm.errors import LLMError
from cardwise_llm.types import (
    Finished,
    LLMEvent,
    LLMRequest,
    TextDelta,
    ToolCall,
    ToolCallReady,
    Usage,
    UsageReport,
)

FakeTurn = Sequence[LLMEvent | LLMError]
"""Events for one `stream()` call. An LLMError item is raised at that point in the stream."""


class FakeChatModel:
    def __init__(self, turns: Sequence[FakeTurn], name: str = "fake:scripted") -> None:
        self._turns = list(turns)
        self._name = name
        self.requests: list[LLMRequest] = []

    @property
    def name(self) -> str:
        return self._name

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        self.requests.append(request)
        if not self._turns:
            raise AssertionError("FakeChatModel has no scripted turns left")
        for item in self._turns.pop(0):
            if isinstance(item, LLMError):
                raise item
            yield item

    @staticmethod
    def text_turn(
        text: str, *, model: str = "fake:scripted", usage: Usage | None = None
    ) -> FakeTurn:
        return [
            TextDelta(text=text),
            UsageReport(usage=usage or Usage(input_tokens=10, output_tokens=5), model=model),
            Finished(reason="stop"),
        ]

    @staticmethod
    def tool_turn(*calls: ToolCall, model: str = "fake:scripted") -> FakeTurn:
        return [
            *(ToolCallReady(call=c) for c in calls),
            UsageReport(usage=Usage(input_tokens=10, output_tokens=5), model=model),
            Finished(reason="tool_calls"),
        ]
