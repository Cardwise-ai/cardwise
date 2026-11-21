from collections.abc import AsyncIterator, Sequence
from datetime import UTC, date, datetime
from uuid import uuid4

import anyio
import pytest

from cardwise_api.agent.loop import AgentLimits, ChatAgent
from cardwise_api.agent.port import AgentEvent, AgentRequest, AgentUsage
from cardwise_api.agent.prompt import FINAL_TURN_NOTE, NO_ANSWER_TEXT, TOOL_LIMIT_RESULT
from cardwise_api.agent.tools import TOOL_SPECS
from cardwise_api.fake_backend import FakeCardBackend, hit
from cardwise_api.models import MessageOut, Ruling
from cardwise_api.stream_events import CardsEvent, TextEvent, ToolEvent
from cardwise_core.cards import Color
from cardwise_llm import (
    ErrorKind,
    FakeChatModel,
    LLMError,
    LLMEvent,
    LLMRequest,
    Role,
    TextDelta,
    ToolCall,
)

CULTIVATE = hit(
    "Cultivate",
    type_line="Sorcery",
    text="Search your library for up to two basic land cards.",
    colors=[Color.GREEN],
)
SOL_RING = hit("Sol Ring", type_line="Artifact", text="{T}: Add {C}{C}.")
BOLT = hit("Lightning Bolt", type_line="Instant", text="deals 3 damage", colors=[Color.RED])


def backend(**kwargs: float) -> FakeCardBackend:
    return FakeCardBackend(
        [CULTIVATE, SOL_RING, BOLT],
        rulings={
            SOL_RING.oracle_id: [
                Ruling(published_at=date(2004, 10, 4), source="wotc", text="Mana ability.")
            ]
        },
        **kwargs,
    )


def search(n: int = 1, text: str = "search") -> ToolCall:
    return ToolCall(id=f"call-{n}", name="search_cards", arguments={"text": text})


def request(question: str = "Green ramp?", history: Sequence[MessageOut] = ()) -> AgentRequest:
    return AgentRequest(chat_id=uuid4(), history=history, question=question)


async def run(
    agent: ChatAgent, req: AgentRequest | None = None
) -> tuple[list[AgentEvent], LLMError | None]:
    events: list[AgentEvent] = []
    try:
        async for event in agent.answer(req or request()):
            events.append(event)
    except LLMError as exc:
        return events, exc
    return events, None


def text_of(events: Sequence[AgentEvent]) -> str:
    return "".join(e.text for e in events if isinstance(e, TextEvent))


def cards_of(events: Sequence[AgentEvent]) -> list[str]:
    (cards,) = [e for e in events if isinstance(e, CardsEvent)]
    return [c.name for c in cards.cards]


def tool_messages(req: LLMRequest) -> list[str]:
    return [m.content for m in req.messages if m.role is Role.TOOL]


async def test_a_tool_round_trip_grounds_the_answer_and_lists_its_cards() -> None:
    model = FakeChatModel(
        [
            FakeChatModel.tool_turn(search(text="library basic land")),
            FakeChatModel.text_turn(
                f"Run [[{CULTIVATE.oracle_id}|Cultivate]], not [[{uuid4()}|Explosive Vegetation]]."
            ),
        ]
    )
    cards = backend()
    events, error = await run(ChatAgent(model, cards))

    assert error is None
    assert events[0] == ToolEvent(name="search_cards", status="running")
    assert events[1] == ToolEvent(name="search_cards", status="done")
    assert text_of(events) == f"Run [[{CULTIVATE.oracle_id}|Cultivate]], not Explosive Vegetation."
    assert cards_of(events) == ["Cultivate"]
    assert events[-1] == AgentUsage(model="fake:scripted", input_tokens=20, output_tokens=10)

    first, second = model.requests
    assert first.tools == TOOL_SPECS
    assert first.messages[0].role is Role.SYSTEM
    (result,) = tool_messages(second)
    assert result.startswith('<tool_result tool="search_cards">')
    assert f"[[{CULTIVATE.oracle_id}|Cultivate]] {{1}} | Sorcery | identity G" in result


async def test_rulings_and_card_lookups_are_compact() -> None:
    model = FakeChatModel(
        [
            FakeChatModel.tool_turn(
                ToolCall(id="a", name="get_card", arguments={"name": "sol ring"}),
                ToolCall(
                    id="b", name="get_rulings", arguments={"oracle_id": str(SOL_RING.oracle_id)}
                ),
            ),
            FakeChatModel.text_turn("ok"),
        ]
    )
    await run(ChatAgent(model, backend()))
    card, rulings = tool_messages(model.requests[1])
    assert f"[[{SOL_RING.oracle_id}|Sol Ring]]" in card
    assert "{T}: Add {C}{C}." in card
    assert "- 2004-10-04: Mana ability." in rulings


async def test_tool_rounds_are_capped_and_the_last_turn_gets_no_tools() -> None:
    turns = [FakeChatModel.tool_turn(search(2 * i), search(2 * i + 1)) for i in range(4)]
    model = FakeChatModel([*turns, FakeChatModel.text_turn("Done.")])
    cards = backend()
    events, error = await run(ChatAgent(model, cards, limits=AgentLimits(max_tool_calls=20)))

    assert error is None
    assert len(cards.calls) == 8
    assert [bool(r.tools) for r in model.requests] == [True, True, True, True, False]
    assert tool_messages(model.requests[4])[-1].endswith(FINAL_TURN_NOTE)
    assert text_of(events) == "Done."


async def test_tool_calls_are_capped_in_total() -> None:
    model = FakeChatModel(
        [
            FakeChatModel.tool_turn(*(search(i) for i in range(10))),
            FakeChatModel.text_turn("Done."),
        ]
    )
    cards = backend()
    await run(ChatAgent(model, cards))

    assert len(cards.calls) == 8
    results = tool_messages(model.requests[1])
    assert results[8:] == [TOOL_LIMIT_RESULT, TOOL_LIMIT_RESULT + FINAL_TURN_NOTE]
    assert model.requests[1].tools == ()


async def test_tool_calls_run_one_at_a_time() -> None:
    model = FakeChatModel(
        [
            FakeChatModel.tool_turn(*(search(i) for i in range(4))),
            FakeChatModel.text_turn("Done."),
        ]
    )
    cards = backend(delay_s=0.01)
    events, _ = await run(ChatAgent(model, cards))

    assert cards.max_active == 1
    statuses = [e.status for e in events if isinstance(e, ToolEvent)]
    assert statuses == ["running", "done"] * 4


async def test_tool_calls_in_a_turn_without_tools_are_ignored() -> None:
    model = FakeChatModel([FakeChatModel.tool_turn(search())])
    cards = backend()
    events, error = await run(ChatAgent(model, cards, limits=AgentLimits(max_tool_rounds=0)))

    assert error is None
    assert cards.calls == []
    assert text_of(events) == NO_ANSWER_TEXT
    assert cards_of(events) == []


async def test_one_bad_call_is_corrected_and_a_second_ends_tool_use() -> None:
    bad = ToolCall(id="bad", name="get_rulings", arguments={"oracle_id": "nope"})
    unknown = ToolCall(id="unknown", name="draw_cards", arguments={})
    model = FakeChatModel(
        [
            FakeChatModel.tool_turn(bad),
            FakeChatModel.tool_turn(unknown),
            FakeChatModel.text_turn("Sorry."),
        ]
    )
    events, error = await run(ChatAgent(model, backend()))

    assert error is None
    assert "Invalid arguments: oracle_id" in tool_messages(model.requests[1])[0]
    assert model.requests[1].tools == TOOL_SPECS
    assert "Unknown tool" in tool_messages(model.requests[2])[-1]
    assert model.requests[2].tools == ()
    assert [e.name for e in events if isinstance(e, ToolEvent)] == ["get_rulings", "get_rulings"]


async def test_text_from_several_turns_is_separated() -> None:
    model = FakeChatModel(
        [
            [TextDelta(text="Let me look."), *FakeChatModel.tool_turn(search())],
            FakeChatModel.text_turn("Found it."),
        ]
    )
    events, _ = await run(ChatAgent(model, backend()))
    assert text_of(events) == "Let me look.\n\nFound it."


async def test_a_model_error_still_reports_cards_and_usage_then_raises() -> None:
    boom = LLMError(ErrorKind.PROVIDER_DOWN, "down", model="fake:scripted")
    model = FakeChatModel(
        [
            FakeChatModel.tool_turn(search(text="library")),
            [TextDelta(text=f"[[{CULTIVATE.oracle_id}|Cultivate]] then"), boom],
        ]
    )
    events, error = await run(ChatAgent(model, backend()))

    assert error is boom
    assert cards_of(events) == ["Cultivate"]
    assert isinstance(events[-1], AgentUsage)
    assert events[-1].input_tokens == 10


class HangingModel:
    name = "fake:hanging"

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        yield TextDelta(text="Thinking")
        await anyio.sleep_forever()


@pytest.mark.parametrize("where", ["model", "tool"])
async def test_the_deadline_ends_the_answer_as_a_timeout(where: str) -> None:
    limits = AgentLimits(deadline_s=0.2, answer_reserve_s=0)
    if where == "model":
        agent = ChatAgent(HangingModel(), backend(), limits=limits)
    else:
        model = FakeChatModel([FakeChatModel.tool_turn(search())])
        agent = ChatAgent(model, backend(delay_s=5), limits=limits)

    with anyio.fail_after(2):
        events, error = await run(agent)

    assert error is not None
    assert error.kind is ErrorKind.TIMEOUT
    assert isinstance(events[-2], CardsEvent)
    assert isinstance(events[-1], AgentUsage)


async def test_deck_constraints_from_history_and_current_question_reach_the_model() -> None:
    def said(role: str, content: str) -> MessageOut:
        return MessageOut.model_validate(
            {
                "id": uuid4(),
                "role": role,
                "content": content,
                "status": "complete",
                "cards": [],
                "created_at": datetime.now(UTC),
            }
        )

    constraints = (
        "My commander is Atraxa. Keep cards within WUBG, include Sol Ring, focus on "
        "+1/+1 counters, stay under $100, prioritize ramp, and exclude tutors."
    )
    history = [
        said("user", constraints),
        said("assistant", "I'll keep those deck constraints in mind."),
    ]
    model = FakeChatModel([FakeChatModel.text_turn("Because.")])
    await run(ChatAgent(model, backend()), request("What ramp should I add?", history))
    (sent,) = model.requests
    assert [m.role for m in sent.messages] == [
        Role.SYSTEM,
        Role.USER,
        Role.ASSISTANT,
        Role.USER,
    ]
    assert sent.messages[1].content == constraints
    assert sent.messages[2].content == "I'll keep those deck constraints in mind."
    assert sent.messages[-1].content == "What ramp should I add?"
