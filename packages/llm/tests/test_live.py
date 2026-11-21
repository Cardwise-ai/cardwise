"""Live smoke test against the real free tiers. Opt in with `pytest -m live`; needs API keys."""

import os
from pathlib import Path

import pytest

from cardwise_llm import (
    ChatModel,
    Finished,
    LLMRequest,
    Message,
    ToolSpec,
    UsageReport,
    build_chat_model,
    complete,
    load_llm_config,
)

pytestmark = pytest.mark.live

GEMINI_MODEL = os.environ.get("CARDWISE_LIVE_GEMINI_MODEL", "gemini-3.5-flash-lite")
OPENROUTER_MODEL = os.environ.get(
    "CARDWISE_LIVE_OPENROUTER_MODEL", "nvidia/nemotron-3.5-super-vl:free"
)

SEARCH = ToolSpec(
    name="search_cards",
    description="Search Magic: The Gathering cards by rules text.",
    parameters={
        "type": "object",
        "properties": {"text": {"type": "string", "description": "Words in the rules text."}},
        "required": ["text"],
    },
)


def _live_model(provider: str) -> ChatModel:
    from cardwise_llm.adapters.pydantic_ai_adapter import gemini, openrouter

    env = {"gemini": "CARDWISE_GEMINI_API_KEY", "openrouter": "CARDWISE_OPENROUTER_API_KEY"}
    key = os.environ.get(env[provider], "").strip()
    if not key:
        pytest.skip(f"{env[provider]} is not set")
    if provider == "gemini":
        return gemini(GEMINI_MODEL, api_key=key)
    return openrouter(OPENROUTER_MODEL, api_key=key)


@pytest.mark.parametrize("provider", ["gemini", "openrouter"])
async def test_live_text_turn(provider: str) -> None:
    model = _live_model(provider)
    response = await complete(
        model,
        LLMRequest(
            messages=(Message.user("Name one green Magic: The Gathering card. One line."),),
            max_output_tokens=200,
            timeout_s=60,
        ),
    )
    assert response.text.strip()
    assert response.finish_reason in ("stop", "length")


@pytest.mark.parametrize("provider", ["gemini", "openrouter"])
async def test_live_tool_turn(provider: str) -> None:
    model = _live_model(provider)
    response = await complete(
        model,
        LLMRequest(
            messages=(
                Message.system("Always call search_cards before answering."),
                Message.user("Find cards that give all creatures trample."),
            ),
            tools=(SEARCH,),
            max_output_tokens=400,
            timeout_s=60,
        ),
    )
    assert response.finish_reason == "tool_calls"
    assert response.tool_calls[0].name == "search_cards"
    assert isinstance(response.tool_calls[0].arguments.get("text"), str)


async def test_live_configured_chain() -> None:
    config = load_llm_config(Path(__file__).parents[3] / "api" / "llm.toml")
    missing = [entry.key_env for entry in config.chain if not os.environ.get(entry.key_env)]
    if missing:
        pytest.skip(f"{', '.join(sorted(set(missing)))} not set")
    events = [
        event
        async for event in build_chat_model(config).stream(
            LLMRequest(messages=(Message.user("Say hi in three words."),), max_output_tokens=50)
        )
    ]
    assert isinstance(events[-1], Finished)
    answered = [event.model for event in events if isinstance(event, UsageReport)]
    assert answered
    assert answered[0] in {entry.display_name for entry in config.chain}
