"""The one error type adapters raise. Provider exceptions never leave an adapter."""

from enum import StrEnum


class ErrorKind(StrEnum):
    RATE_LIMIT = "rate_limit"
    QUOTA_EXHAUSTED = "quota_exhausted"
    AUTH = "auth"
    TIMEOUT = "timeout"
    CONTEXT_TOO_LONG = "context_too_long"
    BAD_REQUEST = "bad_request"
    BAD_TOOL_CALL = "bad_tool_call"
    CONTENT_FILTERED = "content_filtered"
    PROVIDER_DOWN = "provider_down"


RETRYABLE_KINDS = frozenset({ErrorKind.RATE_LIMIT, ErrorKind.TIMEOUT, ErrorKind.PROVIDER_DOWN})
"""Worth retrying on the same model. QUOTA_EXHAUSTED is not: it moves straight to the next model."""

FALLBACK_KINDS = RETRYABLE_KINDS | {ErrorKind.QUOTA_EXHAUSTED}
"""Worth trying the next model in the chain once retries are used up."""


class LLMError(Exception):
    def __init__(
        self,
        kind: ErrorKind,
        message: str,
        *,
        model: str,
        retry_after_s: float | None = None,
    ) -> None:
        super().__init__(f"[{model}] {kind}: {message}")
        self.kind = kind
        self.model = model
        self.retry_after_s = retry_after_s

    @property
    def retryable(self) -> bool:
        return self.kind in RETRYABLE_KINDS

    @property
    def allows_fallback(self) -> bool:
        return self.kind in FALLBACK_KINDS
