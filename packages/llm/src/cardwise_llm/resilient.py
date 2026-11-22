"""A ChatModel that retries and falls back over an ordered chain of models.

Rules, in order:
1. Before every attempt the QuotaStore must grant a request for that model; if it refuses, the
   model is skipped (no provider call, so no provider 429).
2. RATE_LIMIT, TIMEOUT and PROVIDER_DOWN are retried on the same model up to
   `policy.max_attempts` attempts, waiting a full-jitter backoff, or the provider's
   `retry_after_s` if longer. A requested wait above `policy.max_retry_after_s` is not waited
   out: the chain moves to the next model instead.
3. QUOTA_EXHAUSTED marks the model exhausted until its quota day resets and moves straight to
   the next model.
4. Every other kind (AUTH, BAD_REQUEST, BAD_TOOL_CALL, CONTEXT_TOO_LONG, CONTENT_FILTERED) is
   raised at once: another attempt would fail the same way or hide a configuration error.
5. Once any event of an attempt has been yielded to the caller, that attempt is committed: a
   later failure is raised as is, never retried or sent to another model. A model turn is not
   idempotent for the caller (it may have shown text or started tools), so replaying it could
   duplicate output.

The model that answered is always surfaced as `UsageReport.model`; if it reported no usage, one
`UsageReport` with `unmeasured=True` is added before `Finished`.
"""

import asyncio
import logging
import random
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Sequence
from contextlib import aclosing
from dataclasses import dataclass, field
from typing import Annotated

from pydantic import Field

from cardwise_llm.errors import ErrorKind, LLMError
from cardwise_llm.port import ChatModel
from cardwise_llm.quota import QuotaLimits, QuotaStore
from cardwise_llm.types import Finished, LLMEvent, LLMRequest, Model, Usage, UsageReport

logger = logging.getLogger(__name__)


class RetryPolicy(Model):
    max_attempts: Annotated[int, Field(ge=1, le=5)] = 2
    """Attempts per model, the first one included."""
    base_delay_s: Annotated[float, Field(ge=0, le=60)] = 0.5
    max_delay_s: Annotated[float, Field(ge=0, le=60)] = 8.0
    max_retry_after_s: Annotated[float, Field(ge=0, le=120)] = 20.0

    def backoff(self, attempt: int, rand: Callable[[], float]) -> float:
        """Full jitter: uniform in [0, min(max_delay, base * 2^(attempt-1)))."""
        return rand() * min(self.max_delay_s, self.base_delay_s * 2.0 ** (attempt - 1))


@dataclass(frozen=True)
class ChainLink:
    model: ChatModel
    limits: QuotaLimits = field(default_factory=QuotaLimits)


class ResilientModel:
    def __init__(
        self,
        chain: Sequence[ChatModel | ChainLink],
        *,
        policy: RetryPolicy | None = None,
        quota: QuotaStore | None = None,
        sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
        rand: Callable[[], float] = random.random,
    ) -> None:
        if not chain:
            raise ValueError("ResilientModel needs at least one model")
        self._chain = [link if isinstance(link, ChainLink) else ChainLink(link) for link in chain]
        self._policy = policy or RetryPolicy()
        self._quota = quota
        self._sleep = sleep
        self._rand = rand
        self._name = "resilient:" + ",".join(link.model.name for link in self._chain)

    @property
    def name(self) -> str:
        return self._name

    @property
    def models(self) -> tuple[str, ...]:
        return tuple(link.model.name for link in self._chain)

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        last_error: LLMError | None = None
        for link in self._chain:
            error: LLMError | None = None
            async with aclosing(self._try_model(link, request)) as items:
                async for item in items:
                    if isinstance(item, LLMError):
                        error = item
                        break
                    yield item
            if error is None:
                return
            last_error = error
            logger.info("moving on from %s after %s", link.model.name, error.kind)
        if last_error is None:
            raise LLMError(
                ErrorKind.PROVIDER_DOWN, "no model in the chain answered", model=self.name
            )
        raise last_error

    async def _try_model(
        self, link: ChainLink, request: LLMRequest
    ) -> AsyncGenerator[LLMEvent | LLMError]:
        """Yield one model's answer, or end by yielding the LLMError that lets the chain move on.

        Errors that must not fall back are raised instead.
        """
        name = link.model.name
        quota = self._quota
        for attempt in range(1, self._policy.max_attempts + 1):
            if quota is not None and not await quota.reserve(name, link.limits):
                logger.info("skipping %s: local budget used up", name)
                yield LLMError(ErrorKind.QUOTA_EXHAUSTED, "local budget used up", model=name)
                return
            committed = False
            reported = False
            events = link.model.stream(request)
            try:
                async for event in events:
                    if isinstance(event, UsageReport):
                        reported = True
                        if quota is not None:
                            await quota.record_usage(name, link.limits, event.usage)
                    elif isinstance(event, Finished) and not reported:
                        committed = True
                        yield UsageReport(usage=Usage(unmeasured=True), model=name)
                    committed = True
                    yield event
            except LLMError as error:
                if committed:
                    raise
                if error.kind is ErrorKind.QUOTA_EXHAUSTED:
                    if quota is not None:
                        await quota.mark_exhausted(name, link.limits)
                    yield error
                    return
                if not error.retryable:
                    raise
                delay = self._delay(error, attempt)
                if delay is None:
                    yield error
                    return
                logger.info("retrying %s after %s in %.2fs", name, error.kind, delay)
                await self._sleep(delay)
                continue
            finally:
                await _close(events)
            if attempt > 1:
                logger.info("%s answered on attempt %d", name, attempt)
            return

    def _delay(self, error: LLMError, attempt: int) -> float | None:
        """Seconds to wait before retrying, or None to move on to the next model."""
        if attempt >= self._policy.max_attempts:
            return None
        delay = self._policy.backoff(attempt, self._rand)
        if error.retry_after_s is not None:
            if error.retry_after_s > self._policy.max_retry_after_s:
                return None
            delay = max(delay, error.retry_after_s)
        return delay


async def _close(events: AsyncIterator[LLMEvent]) -> None:
    """Close the model's stream now, so an abandoned attempt releases its HTTP connection."""
    aclose = getattr(events, "aclose", None)
    if aclose is not None:
        await aclose()
