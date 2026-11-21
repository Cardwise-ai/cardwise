"""Per-model request and token budgets, so the chain skips a model before its free tier refuses.

`QuotaStore` is the port; `InMemoryQuotaStore` serves one process. A Postgres store fits
`app.usage_counters (subject, kind, window_start, count)`: subject = model name, kind =
`llm_requests_day`, `llm_requests_minute`, `llm_tokens_day` or `llm_exhausted`, window_start =
the window start computed below. `reserve` then becomes one
`insert ... on conflict do update set count = count + 1 where count < cap returning` per window,
which keeps the check-and-increment atomic across serverless instances.
"""

from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta
from typing import Annotated, Protocol
from zoneinfo import ZoneInfo

from pydantic import AfterValidator, Field

from cardwise_llm.types import Model, Usage


def _check_zone(name: str) -> str:
    try:
        ZoneInfo(name)
    except (ValueError, KeyError) as exc:
        raise ValueError(f"unknown time zone {name!r}") from exc
    return name


TimeZoneName = Annotated[str, AfterValidator(_check_zone)]
"""An IANA time zone name such as `America/Los_Angeles`."""


class QuotaLimits(Model):
    """Budgets for one model. A missing cap means no local limit."""

    requests_per_day: Annotated[int, Field(gt=0)] | None = None
    requests_per_minute: Annotated[int, Field(gt=0)] | None = None
    tokens_per_day: Annotated[int, Field(gt=0)] | None = None
    day_resets_in: TimeZoneName = "UTC"
    """Time zone whose midnight starts a new day. Gemini resets at midnight Pacific time."""

    def day_start(self, now: datetime) -> datetime:
        local = now.astimezone(ZoneInfo(self.day_resets_in))
        return datetime.combine(local.date(), time(), tzinfo=local.tzinfo).astimezone(UTC)

    def next_day_start(self, now: datetime) -> datetime:
        local = now.astimezone(ZoneInfo(self.day_resets_in))
        tomorrow = local.date() + timedelta(days=1)
        return datetime.combine(tomorrow, time(), tzinfo=local.tzinfo).astimezone(UTC)


class QuotaStore(Protocol):
    async def reserve(self, model: str, limits: QuotaLimits) -> bool:
        """Count one request against `model` if every budget allows it; False means skip it."""
        ...

    async def record_usage(self, model: str, limits: QuotaLimits, usage: Usage) -> None:
        """Add a finished request's tokens to the day's token budget."""
        ...

    async def mark_exhausted(self, model: str, limits: QuotaLimits) -> None:
        """The provider said the quota is gone: skip `model` until its day resets."""
        ...


def _utcnow() -> datetime:
    return datetime.now(UTC)


class InMemoryQuotaStore:
    """Counters for one process. No method awaits, so check-and-increment is atomic."""

    def __init__(self, clock: Callable[[], datetime] = _utcnow) -> None:
        self._clock = clock
        self._counts: dict[tuple[str, str, datetime], int] = {}
        self._exhausted_until: dict[str, datetime] = {}

    def _now(self) -> datetime:
        return self._clock().astimezone(UTC)

    async def reserve(self, model: str, limits: QuotaLimits) -> bool:
        now = self._now()
        until = self._exhausted_until.get(model)
        if until is not None and now < until:
            return False
        day = limits.day_start(now)
        minute = now.replace(second=0, microsecond=0)
        budgets = (
            (("requests_day", day), limits.requests_per_day),
            (("requests_minute", minute), limits.requests_per_minute),
        )
        if any(cap is not None and self._get(model, *key) >= cap for key, cap in budgets):
            return False
        tokens_cap = limits.tokens_per_day
        if tokens_cap is not None and self._get(model, "tokens_day", day) >= tokens_cap:
            return False
        for (kind, window), _cap in budgets:
            self._add(model, kind, window, 1)
        return True

    async def record_usage(self, model: str, limits: QuotaLimits, usage: Usage) -> None:
        tokens = usage.input_tokens + usage.output_tokens
        if tokens:
            self._add(model, "tokens_day", limits.day_start(self._now()), tokens)

    async def mark_exhausted(self, model: str, limits: QuotaLimits) -> None:
        self._exhausted_until[model] = limits.next_day_start(self._now())

    def requests_today(self, model: str, limits: QuotaLimits) -> int:
        return self._get(model, "requests_day", limits.day_start(self._now()))

    def _get(self, model: str, kind: str, window: datetime) -> int:
        return self._counts.get((model, kind, window), 0)

    def _add(self, model: str, kind: str, window: datetime, amount: int) -> None:
        key = (model, kind, window)
        self._counts[key] = self._counts.get(key, 0) + amount
        if len(self._counts) > _PRUNE_ABOVE:
            oldest = self._now() - timedelta(days=2)
            self._counts = {k: v for k, v in self._counts.items() if k[2] >= oldest}


_PRUNE_ABOVE = 4096
