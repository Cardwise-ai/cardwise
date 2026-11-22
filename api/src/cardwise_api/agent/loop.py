"""The agent loop (spec 7.4): model turn, tool calls, results, repeat, within fixed caps.

Caps per answer: `max_tool_rounds` model turns that run tools, `max_tool_calls` tool calls,
and a wall-clock `deadline_s`. Once a cap is reached, or less than `answer_reserve_s` remains,
the next model turn is offered no tools and told to answer. Running out of time is an
LLMError(TIMEOUT), which the route saves as a failed reply.

Tool calls run one at a time: the backend shares the request's single database connection.
An invalid call (unknown tool or bad arguments) gets the validation error back as its result,
so the model can correct it once; a second invalid call ends tool use for the answer.

Text streams through RefFilter, so citations are grounded before they leave the server. The
cards event (linked cards, in citation order) and the usage follow the text.
"""

from collections.abc import AsyncGenerator, AsyncIterator, Coroutine, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Final

import anyio
from pydantic import Field

from cardwise_api.agent.grounding import Grounding, RefFilter
from cardwise_api.agent.port import AgentEvent, AgentRequest, AgentUsage
from cardwise_api.agent.prompt import (
    FINAL_TURN_NOTE,
    NO_ANSWER_TEXT,
    TOOL_LIMIT_RESULT,
    build_system_prompt,
)
from cardwise_api.agent.tools import TOOL_SPECS, is_tool_name, run_tool
from cardwise_api.models import MessageOut, Model
from cardwise_api.retrieval.port import CardBackend
from cardwise_api.stream_events import CardsEvent, TextEvent, ToolEvent
from cardwise_llm import (
    ChatModel,
    ErrorKind,
    LLMError,
    LLMEvent,
    LLMRequest,
    Message,
    TextDelta,
    ToolCall,
    ToolCallReady,
    UsageReport,
)

TURN_SEPARATOR: Final = "\n\n"


@asynccontextmanager
async def _closing(stream: AsyncIterator[LLMEvent]) -> AsyncGenerator[AsyncIterator[LLMEvent]]:
    """Close the model stream even when the loop leaves it early (deadline, error)."""
    try:
        yield stream
    finally:
        aclose = getattr(stream, "aclose", None)
        if aclose is not None:
            await aclose()


class AgentLimits(Model):
    max_tool_rounds: Annotated[int, Field(ge=0, le=10)] = 4
    max_tool_calls: Annotated[int, Field(ge=0, le=20)] = 8
    deadline_s: Annotated[float, Field(gt=0, le=300)] = 60.0
    answer_reserve_s: Annotated[float, Field(ge=0, le=120)] = 15.0
    """Tools are offered only while more than this remains, leaving time for the answer."""
    model_timeout_s: Annotated[float, Field(gt=0, le=120)] = 45.0
    max_output_tokens: Annotated[int, Field(gt=0, le=8192)] = 2048
    temperature: Annotated[float, Field(ge=0, le=2)] = 0.3


class DeadlineExceededError(Exception):
    pass


@dataclass
class _Tally:
    model: str
    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, report: UsageReport) -> None:
        self.model = report.model
        self.input_tokens += report.usage.input_tokens
        self.output_tokens += report.usage.output_tokens

    def usage(self) -> AgentUsage:
        return AgentUsage(
            model=self.model, input_tokens=self.input_tokens, output_tokens=self.output_tokens
        )


@dataclass
class _Budget:
    rounds: int = 0
    calls: int = 0
    corrections: int = 1
    tools_on: bool = True


class ChatAgent:
    """Implements the Agent port over one ChatModel and one request's CardBackend."""

    def __init__(
        self, model: ChatModel, backend: CardBackend, *, limits: AgentLimits | None = None
    ) -> None:
        self._model = model
        self._backend = backend
        self._limits = limits or AgentLimits()

    async def answer(self, request: AgentRequest) -> AsyncIterator[AgentEvent]:
        limits = self._limits
        deadline = anyio.current_time() + limits.deadline_s
        grounding = Grounding()
        refs = RefFilter(grounding)
        tally = _Tally(model=self._model.name)
        budget = _Budget(tools_on=limits.max_tool_rounds > 0 and limits.max_tool_calls > 0)
        messages = [
            Message.system(build_system_prompt()),
            *_history(request.history),
            Message.user(request.question),
        ]
        wrote = False
        try:
            while True:
                offer = budget.tools_on and _remaining(deadline) > limits.answer_reserve_s
                text: list[str] = []
                calls: list[ToolCall] = []
                lead = TURN_SEPARATOR if wrote else ""
                model_request = LLMRequest(
                    messages=tuple(messages),
                    tools=TOOL_SPECS if offer else (),
                    max_output_tokens=limits.max_output_tokens,
                    temperature=limits.temperature,
                    timeout_s=max(1.0, min(limits.model_timeout_s, _remaining(deadline))),
                )
                async with _closing(self._model.stream(model_request)) as stream:
                    while (event := await _next(stream, deadline)) is not None:
                        match event:
                            case TextDelta():
                                text.append(event.text)
                                out = refs.feed(event.text)
                                if out:
                                    yield TextEvent(text=lead + out)
                                    lead, wrote = "", True
                            case ToolCallReady():
                                calls.append(event.call)
                            case UsageReport():
                                tally.add(event)
                out = refs.flush()
                if out:
                    yield TextEvent(text=lead + out)
                    wrote = True
                if not offer or not calls:
                    break

                messages.append(Message.assistant("".join(text), tuple(calls)))
                results: list[Message] = []
                budget.rounds += 1
                for call in calls:
                    if budget.calls >= limits.max_tool_calls:
                        results.append(Message.tool_result(call.id, TOOL_LIMIT_RESULT))
                        continue
                    budget.calls += 1
                    known = call.name if is_tool_name(call.name) else None
                    if known:
                        yield ToolEvent(name=known, status="running")
                    outcome = await _within(
                        deadline, run_tool(self._backend, grounding, call.name, call.arguments)
                    )
                    if known:
                        yield ToolEvent(name=known, status="done")
                    if not outcome.valid:
                        if budget.corrections > 0:
                            budget.corrections -= 1
                        else:
                            budget.tools_on = False
                    results.append(Message.tool_result(call.id, outcome.content))
                if budget.rounds >= limits.max_tool_rounds or (
                    budget.calls >= limits.max_tool_calls
                ):
                    budget.tools_on = False
                if not budget.tools_on or _remaining(deadline) <= limits.answer_reserve_s:
                    last = results[-1]
                    results[-1] = Message.tool_result(
                        last.tool_call_id or "", last.content + FINAL_TURN_NOTE
                    )
                messages.extend(results)
        except (LLMError, DeadlineExceededError) as exc:
            out = refs.flush()
            if out:
                yield TextEvent(text=out)
            yield CardsEvent(cards=grounding.cited)
            yield tally.usage()
            if isinstance(exc, LLMError):
                raise
            raise LLMError(
                ErrorKind.TIMEOUT, "answer deadline exceeded", model=tally.model
            ) from exc
        if not wrote:
            yield TextEvent(text=NO_ANSWER_TEXT)
        yield CardsEvent(cards=grounding.cited)
        yield tally.usage()


def _history(history: Sequence[MessageOut]) -> list[Message]:
    return [
        Message.user(m.content) if m.role == "user" else Message.assistant(m.content)
        for m in history
        if m.content.strip()
    ]


def _remaining(deadline: float) -> float:
    return deadline - anyio.current_time()


async def _next(stream: AsyncIterator[LLMEvent], deadline: float) -> LLMEvent | None:
    with anyio.move_on_after(_remaining(deadline)):
        try:
            return await anext(stream)
        except StopAsyncIteration:
            return None
    raise DeadlineExceededError


async def _within[T](deadline: float, step: Coroutine[object, object, T]) -> T:
    with anyio.move_on_after(_remaining(deadline)):
        return await step
    step.close()
    raise DeadlineExceededError
