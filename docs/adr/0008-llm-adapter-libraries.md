# 0008: PydanticAI direct requests for Gemini and OpenRouter, openai SDK for other endpoints

Status: accepted
Date: 2026-11-22

## Context
ADR 0003 keeps our own `ChatModel` port and allows vendor SDKs only in `cardwise_llm.adapters`. Line C needs adapters for the Gemini free tier, OpenRouter free models and any OpenAI-compatible endpoint, with streaming text, whole tool calls, usage and a closed error taxonomy.

## Decision
- Gemini and OpenRouter use PydanticAI's direct API (`pydantic_ai.direct.model_request_stream`) with `GoogleModel` and `OpenRouterModel`, not `Agent`. The port owns the tool loop, so we only need one model request per turn. PydanticAI's typed errors (`ModelRateLimitError`, `ModelQuotaExceededError`, `ModelAuthenticationError`, `ModelContextWindowExceededError`, ...) map almost one-to-one onto `ErrorKind`, and it already handles Gemini thought signatures on tool-call round trips.
- Other OpenAI-compatible endpoints use the `openai` SDK directly (`OpenAICompatAdapter`), so a provider PydanticAI does not know still works with just a base URL.
- Both SDKs run with retries off (`max_retries=0`). `ResilientModel` owns every retry and fallback, so the backoff and quota rules stay in one place.
- The SDKs are built on `httpx2`. Tests inject an `httpx2.AsyncClient` with a `MockTransport` that serves recorded-shape provider replies; `respx` only patches `httpx`, so it is not used.
- The model chain lives in `api/llm.toml`. Keys come only from the environment, named per entry.

## Consequences
- One contract suite runs every adapter and `FakeChatModel` against the same scenarios with no network.
- Provider quirks that PydanticAI does not classify are handled in our mapping: OpenRouter's free-models-per-day 429 becomes `QUOTA_EXHAUSTED`, and the 403 OpenRouter sends for moderation-flagged input becomes `CONTENT_FILTERED` (other 403s stay `AUTH`).
- Upgrading PydanticAI can change its error classes; the contract suite catches that.
