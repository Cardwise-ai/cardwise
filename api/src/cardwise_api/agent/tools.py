"""The agent's tools over a CardBackend (spec 7.4).

Inputs are the frozen contracts in cardwise_core.search (TOOL_INPUTS). Results go back to the
model as compact text wrapped in `<tool_result>`; the system prompt says that is data, not
instructions. Every card in a result is written as the citation the model must copy,
`[[<oracle_id>|<name>]]`, and is recorded in the turn's Grounding.
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal, TypeGuard

import asyncpg
from pydantic import BaseModel, JsonValue, ValidationError

from cardwise_api.agent.grounding import Grounding
from cardwise_api.models import Ruling
from cardwise_api.retrieval.port import CardBackend
from cardwise_core.search import (
    TOOL_INPUTS,
    CardHit,
    CardLookup,
    CardQuery,
    RulingsLookup,
    SimilarQuery,
)
from cardwise_llm import ToolSpec

log: Final = logging.getLogger("cardwise_api.agent")

ToolName = Literal["search_cards", "get_card", "get_rulings", "similar_cards"]

DESCRIPTIONS: Final[dict[ToolName, str]] = {
    "search_cards": (
        "Search the card database. Combine filters; every filter that is set must match. "
        "For a Commander deck, set color_identity_within to the commander's colors and "
        "legal_in to commander."
    ),
    "get_card": "Get one card's full text by exact oracle_id or by name (fuzzy).",
    "get_rulings": "Get the official rulings for one card by oracle_id.",
    "similar_cards": (
        "Find cards similar to one card. by=role: same job in a deck (shared tags). "
        "by=text: similar rules text."
    ),
}

TOOL_SPECS: Final = tuple(
    ToolSpec.from_model(name, DESCRIPTIONS[name], TOOL_INPUTS[name]) for name in DESCRIPTIONS
)

LIST_TEXT_LIMIT: Final = 220
"""Rules text kept per card in search results; get_card returns the full text."""
CARD_TEXT_LIMIT: Final = 1500
MAX_RULINGS: Final = 12
RULING_TEXT_LIMIT: Final = 400

TOOL_ERRORS: Final = (asyncpg.PostgresError, asyncpg.InterfaceError, OSError, TimeoutError)
"""Backend failures reported to the model as a failed tool call instead of ending the answer."""


@dataclass(frozen=True, slots=True)
class ToolOutcome:
    content: str
    valid: bool
    """False when the call named an unknown tool or had invalid arguments."""


def is_tool_name(name: str) -> TypeGuard[ToolName]:
    return name in DESCRIPTIONS


async def run_tool(
    backend: CardBackend, grounding: Grounding, name: str, arguments: Mapping[str, JsonValue]
) -> ToolOutcome:
    if not is_tool_name(name):
        known = ", ".join(DESCRIPTIONS)
        return ToolOutcome(_wrap(name, f"Unknown tool. Available tools: {known}."), valid=False)
    try:
        query = TOOL_INPUTS[name].model_validate(_drop_empty(arguments))
    except ValidationError as exc:
        return ToolOutcome(_wrap(name, f"Invalid arguments: {_problems(exc)}"), valid=False)
    try:
        body = await _execute(backend, grounding, query)
    except TOOL_ERRORS as exc:
        log.error("tool failed", exc_info=exc, extra={"fields": {"tool": name}})
        body = "The card database did not answer. Do not retry this call."
    return ToolOutcome(_wrap(name, body), valid=True)


def _drop_empty(arguments: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    """Models often send null or "" for filters they mean to leave out."""
    return {k: v for k, v in arguments.items() if v is not None and v != ""}


def _problems(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(p) for p in e['loc']) or 'arguments'}: {e['msg']}"
        for e in exc.errors(include_url=False, include_input=False)
    )


async def _execute(backend: CardBackend, grounding: Grounding, query: BaseModel) -> str:
    match query:
        case CardQuery():
            return _hits(grounding, await backend.search(query))
        case SimilarQuery():
            return _hits(grounding, await backend.similar(query))
        case CardLookup():
            hit = await backend.get_card(query)
            if hit is None:
                return "No such card."
            grounding.add(hit)
            return _card(hit, CARD_TEXT_LIMIT)
        case RulingsLookup():
            return _rulings(await backend.get_rulings(query))
    raise TypeError(f"no tool takes {type(query).__name__}")


def _wrap(name: str, body: str) -> str:
    return f'<tool_result tool="{name}">\n{body}\n</tool_result>'


def _hits(grounding: Grounding, hits: list[CardHit]) -> str:
    if not hits:
        return "No cards matched."
    for hit in hits:
        grounding.add(hit)
    cards = "\n".join(f"- {_card(hit, LIST_TEXT_LIMIT)}" for hit in hits)
    return f"{len(hits)} cards:\n{cards}"


def _card(hit: CardHit, text_limit: int) -> str:
    identity = "".join(hit.color_identity) or "colorless"
    facts = [hit.mana_cost, hit.type_line, f"identity {identity}", f"mv {hit.mana_value:g}"]
    if hit.matched_tags:
        facts.append("tags " + ", ".join(hit.matched_tags))
    head = f"[[{hit.oracle_id}|{hit.name}]] " + " | ".join(f for f in facts if f)
    text = _clip(hit.oracle_text.replace("\n\n", " // ").replace("\n", " / "), text_limit)
    return f"{head}\n  {text}" if text else head


def _rulings(rulings: list[Ruling]) -> str:
    if not rulings:
        return "No rulings."
    shown = rulings[-MAX_RULINGS:]
    lines = [f"- {r.published_at}: {_clip(r.text, RULING_TEXT_LIMIT)}" for r in shown]
    more = len(rulings) - len(shown)
    if more:
        lines.insert(0, f"({more} older rulings left out)")
    return "\n".join(lines)


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
