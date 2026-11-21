# 0003: Our own model port, provider SDKs only in adapters

Status: accepted
Date: 2026-11-21

## Context
The POC runs on free tiers (Gemini free tier first, OpenRouter free models as fallback) and will move to paid models later. Free tiers fail often (rate limits, daily quotas), so retry and fallback must be first-class. LiteLLM was rejected after 2026 security advisories and the malicious 1.82.7 and 1.82.8 releases.

## Decision
- `cardwise_llm` defines a small port: `ChatModel.stream(LLMRequest) -> AsyncIterator[LLMEvent]`, Pydantic message and tool types, and a closed `ErrorKind` set that marks errors as retryable and/or allowing fallback.
- Adapters live in `cardwise_llm.adapters` and are the only code allowed to import provider SDKs (`pydantic_ai`, `openai`, `anthropic`, `google.genai`, `litellm`). Ruff rule TID251 enforces this, including submodule imports.
- `FakeChatModel` scripts streams and errors for tests; no test needs a network call unless marked `live`.

## Consequences
- Switching or adding a provider is one adapter plus config.
- We maintain the event mapping per adapter ourselves.
