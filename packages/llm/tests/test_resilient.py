from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest

from cardwise_llm import (
    ChainLink,
    ErrorKind,
    FakeChatModel,
    Finished,
    InMemoryQuotaStore,
    LLMError,
    LLMEvent,
    LLMRequest,
    Message,
    QuotaLimits,
    ResilientModel,
    RetryPolicy,
    TextDelta,
    Usage,
    UsageReport,
    complete,
)

REQUEST = LLMRequest(messages=(Message.user("hi"),))
FAST = RetryPolicy(max_attempts=3, base_delay_s=1, max_delay_s=8, max_retry_after_s=20)


def fake(name: str, *turns: list[LLMEvent | LLMError]) -> FakeChatModel:
    return FakeChatModel(list(turns), name=name)


def answer(name: str) -> list[LLMEvent | LLMError]:
    return list(FakeChatModel.text_turn(f"from {name}", model=name))


def fail(kind: ErrorKind, name: str, retry_after: float | None = None) -> list[LLMEvent | LLMError]:
    return [LLMError(kind, "scripted", model=name, retry_after_s=retry_after)]


class Sleeps:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


def resilient(*chain: FakeChatModel | ChainLink, **kwargs: object) -> tuple[ResilientModel, Sleeps]:
    sleeps = Sleeps()
    model = ResilientModel(chain, policy=FAST, sleep=sleeps, rand=lambda: 0.5, **kwargs)  # type: ignore[arg-type]
    return model, sleeps


async def test_transient_error_is_retried_on_the_same_model() -> None:
    primary = fake(
        "a", fail(ErrorKind.PROVIDER_DOWN, "a"), fail(ErrorKind.TIMEOUT, "a"), answer("a")
    )
    model, sleeps = resilient(primary, fake("b"))

    response = await complete(model, REQUEST)

    assert response.text == "from a"
    assert sleeps.delays == [0.5, 1.0]  # full jitter with rand=0.5: 0.5 * 1, 0.5 * 2


async def test_retry_waits_for_provider_retry_after() -> None:
    model, sleeps = resilient(fake("a", fail(ErrorKind.RATE_LIMIT, "a", 7), answer("a")))
    await complete(model, REQUEST)
    assert sleeps.delays == [7]


async def test_retry_after_above_the_cap_falls_over_without_waiting() -> None:
    model, sleeps = resilient(
        fake("a", fail(ErrorKind.RATE_LIMIT, "a", 3600)), fake("b", answer("b"))
    )
    response = await complete(model, REQUEST)
    assert response.text == "from b"
    assert sleeps.delays == []


async def test_exhausted_retries_fall_back_in_chain_order() -> None:
    down = fail(ErrorKind.PROVIDER_DOWN, "a")
    a = fake("a", down, down, down)
    b = fake("b", fail(ErrorKind.QUOTA_EXHAUSTED, "b"))
    c = fake("c", answer("c"))
    model, _ = resilient(a, b, c)

    events = [event async for event in model.stream(REQUEST)]

    assert len(a.requests) == 3
    assert len(b.requests) == 1, "quota errors are not retried"
    usage = [event for event in events if isinstance(event, UsageReport)]
    assert [report.model for report in usage] == ["c"]
    assert model.models == ("a", "b", "c")
    assert model.name == "resilient:a,b,c"


@pytest.mark.parametrize(
    "kind",
    [
        ErrorKind.AUTH,
        ErrorKind.BAD_REQUEST,
        ErrorKind.BAD_TOOL_CALL,
        ErrorKind.CONTEXT_TOO_LONG,
        ErrorKind.CONTENT_FILTERED,
    ],
)
async def test_non_transient_errors_are_raised_without_fallback(kind: ErrorKind) -> None:
    backup = fake("b", answer("b"))
    model, sleeps = resilient(fake("a", fail(kind, "a")), backup)
    with pytest.raises(LLMError) as raised:
        await complete(model, REQUEST)
    assert raised.value.kind is kind
    assert backup.requests == []
    assert sleeps.delays == []


async def test_failure_after_output_is_never_retried_or_rerouted() -> None:
    partial: list[LLMEvent | LLMError] = [
        TextDelta(text="Hel"),
        LLMError(ErrorKind.PROVIDER_DOWN, "x", model="a"),
    ]
    primary = fake("a", partial, answer("a"))
    backup = fake("b", answer("b"))
    model, _ = resilient(primary, backup)

    seen: list[str] = []
    with pytest.raises(LLMError) as raised:
        await collect_text(model.stream(REQUEST), seen)

    assert raised.value.kind is ErrorKind.PROVIDER_DOWN
    assert seen == ["Hel"]
    assert len(primary.requests) == 1
    assert backup.requests == []


async def collect_text(events: AsyncIterator[LLMEvent], seen: list[str]) -> None:
    async for event in events:
        if isinstance(event, TextDelta):
            seen.append(event.text)


async def test_last_error_is_raised_when_every_model_fails() -> None:
    model, _ = resilient(
        fake("a", fail(ErrorKind.QUOTA_EXHAUSTED, "a")),
        fake("b", fail(ErrorKind.RATE_LIMIT, "b", 999)),
    )
    with pytest.raises(LLMError) as raised:
        await complete(model, REQUEST)
    assert raised.value.kind is ErrorKind.RATE_LIMIT
    assert raised.value.model == "b"


async def test_missing_usage_is_reported_as_unmeasured_for_the_answering_model() -> None:
    model, _ = resilient(fake("a", [TextDelta(text="ok"), Finished(reason="stop")]))
    events = [event async for event in model.stream(REQUEST)]
    assert events[-2] == UsageReport(usage=Usage(unmeasured=True), model="a")
    assert isinstance(events[-1], Finished)


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


async def test_quota_store_skips_models_without_budget() -> None:
    store = InMemoryQuotaStore(clock=Clock(datetime(2026, 5, 1, 12, tzinfo=UTC)))
    one_a_day = QuotaLimits(requests_per_day=1)
    a = fake("a", answer("a"), answer("a"))
    b = fake("b", answer("b"))
    model, _ = resilient(ChainLink(a, one_a_day), ChainLink(b), quota=store)

    assert (await complete(model, REQUEST)).text == "from a"
    assert (await complete(model, REQUEST)).text == "from b"
    assert len(a.requests) == 1, "the exhausted model is not called at all"


async def test_provider_quota_error_marks_the_model_exhausted() -> None:
    store = InMemoryQuotaStore(clock=Clock(datetime(2026, 5, 1, 12, tzinfo=UTC)))
    a = fake("a", fail(ErrorKind.QUOTA_EXHAUSTED, "a"))
    b = fake("b", answer("b"), answer("b"))
    model, _ = resilient(a, b, quota=store)

    await complete(model, REQUEST)
    await complete(model, REQUEST)

    assert len(a.requests) == 1


async def test_every_model_skipped_by_quota_raises_quota_exhausted() -> None:
    store = InMemoryQuotaStore()
    a = fake("a")
    await store.mark_exhausted("a", QuotaLimits())
    model, _ = resilient(a, quota=store)
    with pytest.raises(LLMError) as raised:
        await complete(model, REQUEST)
    assert raised.value.kind is ErrorKind.QUOTA_EXHAUSTED
    assert a.requests == []


async def test_usage_is_recorded_against_the_token_budget() -> None:
    store = InMemoryQuotaStore(clock=Clock(datetime(2026, 5, 1, 12, tzinfo=UTC)))
    limits = QuotaLimits(tokens_per_day=15)
    a = fake("a", answer("a"), answer("a"))  # each answer reports 10 + 5 tokens
    b = fake("b", answer("b"))
    model, _ = resilient(ChainLink(a, limits), b, quota=store)

    assert (await complete(model, REQUEST)).text == "from a"
    assert (await complete(model, REQUEST)).text == "from b"


def test_empty_chain_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one"):
        ResilientModel([])
