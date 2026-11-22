from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from cardwise_llm import InMemoryQuotaStore, QuotaLimits, Usage


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


# 07:59 UTC on 2 May 2026 is 00:59 Pacific (PDT, UTC-7); Pacific midnight is 07:00 UTC.
PACIFIC = QuotaLimits(requests_per_day=2, day_resets_in="America/Los_Angeles")


async def test_daily_requests_reset_at_the_configured_midnight() -> None:
    clock = Clock(datetime(2026, 5, 2, 6, 30, tzinfo=UTC))  # 23:30 Pacific on 1 May
    store = InMemoryQuotaStore(clock=clock)

    assert await store.reserve("m", PACIFIC)
    assert await store.reserve("m", PACIFIC)
    assert not await store.reserve("m", PACIFIC)

    clock.now = datetime(2026, 5, 2, 7, 0, tzinfo=UTC)  # a UTC day would not have reset here
    assert await store.reserve("m", PACIFIC)
    assert store.requests_today("m", PACIFIC) == 1


async def test_minute_window() -> None:
    clock = Clock(datetime(2026, 5, 2, 12, 0, 10, tzinfo=UTC))
    store = InMemoryQuotaStore(clock=clock)
    limits = QuotaLimits(requests_per_minute=1)

    assert await store.reserve("m", limits)
    assert not await store.reserve("m", limits)
    clock.now += timedelta(seconds=50)
    assert await store.reserve("m", limits)


async def test_refused_reservation_does_not_count() -> None:
    clock = Clock(datetime(2026, 5, 2, 12, tzinfo=UTC))
    store = InMemoryQuotaStore(clock=clock)
    limits = QuotaLimits(requests_per_day=5, requests_per_minute=1)

    assert await store.reserve("m", limits)
    assert not await store.reserve("m", limits)
    assert store.requests_today("m", limits) == 1


async def test_token_budget() -> None:
    store = InMemoryQuotaStore(clock=Clock(datetime(2026, 5, 2, 12, tzinfo=UTC)))
    limits = QuotaLimits(tokens_per_day=100)

    assert await store.reserve("m", limits)
    await store.record_usage("m", limits, Usage(input_tokens=90, output_tokens=10))
    assert not await store.reserve("m", limits)
    assert await store.reserve("other", limits), "budgets are per model"


async def test_exhausted_model_is_skipped_until_its_day_resets() -> None:
    clock = Clock(datetime(2026, 5, 2, 12, tzinfo=UTC))
    store = InMemoryQuotaStore(clock=clock)

    await store.mark_exhausted("m", PACIFIC)
    assert not await store.reserve("m", PACIFIC)
    clock.now = datetime(2026, 5, 3, 6, 59, tzinfo=UTC)
    assert not await store.reserve("m", PACIFIC)
    clock.now = datetime(2026, 5, 3, 7, 0, tzinfo=UTC)
    assert await store.reserve("m", PACIFIC)


@pytest.mark.parametrize(
    "bad",
    [{"requests_per_day": 0}, {"tokens_per_day": -1}, {"day_resets_in": "Mars/Olympus_Mons"}],
)
def test_limits_validation(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        QuotaLimits.model_validate(bad)
