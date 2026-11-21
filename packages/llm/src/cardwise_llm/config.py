"""`llm.toml` loading and the factory that turns it into a ResilientModel.

The file holds providers, model ids, order, budgets and timeouts. API keys never live in it: each
entry names the environment variable that holds its key, and the factory reads it at startup.
"""

import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Literal, Self

import httpx2
from pydantic import AnyHttpUrl, Field, ValidationError, model_validator

from cardwise_llm.port import ChatModel
from cardwise_llm.quota import QuotaLimits, QuotaStore, TimeZoneName
from cardwise_llm.resilient import ChainLink, ResilientModel, RetryPolicy
from cardwise_llm.types import Model

Provider = Literal["gemini", "openrouter", "openai_compat"]

DEFAULT_KEY_ENV: dict[str, str] = {
    "gemini": "CARDWISE_GEMINI_API_KEY",
    "openrouter": "CARDWISE_OPENROUTER_API_KEY",
}

EnvName = Annotated[str, Field(pattern=r"^CARDWISE_[A-Z0-9_]+$")]
PositiveCap = Annotated[int, Field(gt=0)]


class LLMConfigError(ValueError):
    """The LLM config or its environment is invalid; the app must not start."""


class ChainEntry(Model):
    provider: Provider
    model: Annotated[str, Field(min_length=1, max_length=200, pattern=r"^\S+$")]
    label: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$")] | None = None
    """Provider name used in `provider:model` for openai_compat entries, e.g. `groq`."""
    base_url: AnyHttpUrl | None = None
    api_key_env: EnvName | None = None
    timeout_s: Annotated[float, Field(gt=0, le=120)] = 45
    """Upper bound for one request to this model; a request's own `timeout_s` can only lower it."""
    daily_request_cap: PositiveCap | None = None
    minute_request_cap: PositiveCap | None = None
    daily_token_cap: PositiveCap | None = None
    day_resets_in: TimeZoneName = "UTC"

    @model_validator(mode="after")
    def _check_provider_fields(self) -> Self:
        if self.provider == "openai_compat":
            if self.base_url is None or self.api_key_env is None:
                raise ValueError("openai_compat entries need base_url and api_key_env")
        elif self.base_url is not None or self.label is not None:
            raise ValueError(f"base_url and label are only for openai_compat, not {self.provider}")
        return self

    @property
    def key_env(self) -> str:
        return self.api_key_env or DEFAULT_KEY_ENV[self.provider]

    @property
    def display_name(self) -> str:
        return f"{self.label or self.provider}:{self.model}"

    @property
    def limits(self) -> QuotaLimits:
        return QuotaLimits(
            requests_per_day=self.daily_request_cap,
            requests_per_minute=self.minute_request_cap,
            tokens_per_day=self.daily_token_cap,
            day_resets_in=self.day_resets_in,
        )


class LLMConfig(Model):
    policy: RetryPolicy = Field(default_factory=RetryPolicy)
    chain: Annotated[tuple[ChainEntry, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def _check_unique(self) -> Self:
        names = [entry.display_name for entry in self.chain]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"chain lists {', '.join(duplicates)} more than once")
        return self


def load_llm_config(path: Path) -> LLMConfig:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise LLMConfigError(f"{path}: {exc}") from exc
    try:
        return LLMConfig.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or '(root)'}: {error['msg']}"
            for error in exc.errors(include_url=False)
        )
        raise LLMConfigError(f"{path}: {problems}") from exc


def build_chat_model(
    config: LLMConfig,
    *,
    env: Mapping[str, str] | None = None,
    quota: QuotaStore | None = None,
    http_client: httpx2.AsyncClient | None = None,
) -> ResilientModel:
    """Build the chain. Fails fast when an entry's API key is missing from the environment."""
    environ = os.environ if env is None else env
    missing = [
        f"{entry.key_env} (for {entry.display_name})"
        for entry in config.chain
        if not environ.get(entry.key_env, "").strip()
    ]
    if missing:
        raise LLMConfigError("missing API keys: " + ", ".join(missing))
    links = [
        ChainLink(_build_entry(entry, environ[entry.key_env].strip(), http_client), entry.limits)
        for entry in config.chain
    ]
    return ResilientModel(links, policy=config.policy, quota=quota)


def _build_entry(
    entry: ChainEntry, api_key: str, http_client: httpx2.AsyncClient | None
) -> ChatModel:
    # Imported here so `import cardwise_llm` stays light: SDKs load only when a chain is built.
    from cardwise_llm.adapters.openai_compat import OpenAICompatAdapter
    from cardwise_llm.adapters.pydantic_ai_adapter import gemini, openrouter

    match entry.provider:
        case "gemini":
            return gemini(
                entry.model, api_key=api_key, http_client=http_client, max_timeout_s=entry.timeout_s
            )
        case "openrouter":
            return openrouter(
                entry.model, api_key=api_key, http_client=http_client, max_timeout_s=entry.timeout_s
            )
        case "openai_compat":
            return OpenAICompatAdapter(
                entry.model,
                base_url=str(entry.base_url),
                api_key=api_key,
                provider=entry.label or entry.provider,
                http_client=http_client,
                max_timeout_s=entry.timeout_s,
            )
