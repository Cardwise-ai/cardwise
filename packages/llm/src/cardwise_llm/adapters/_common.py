"""Provider-neutral helpers shared by the adapters. No vendor imports here."""

import json
import logging

from pydantic import ValidationError

from cardwise_llm.errors import ErrorKind, LLMError
from cardwise_llm.types import Message, Role, ToolCall

logger = logging.getLogger("cardwise_llm.adapters")

_DAILY_CAP_HINTS = ("per-day", "per_day", "per day", "daily")


def mentions_daily_cap(text: str) -> bool:
    """A 429 that names a daily cap will not clear by waiting seconds: it is quota, not rate."""
    lowered = text.lower()
    return any(hint in lowered for hint in _DAILY_CAP_HINTS)


def tool_names_by_call_id(messages: tuple[Message, ...]) -> dict[str, str]:
    """Tool results only carry the call id; some providers also need the tool's name."""
    return {
        call.id: call.name
        for message in messages
        if message.role is Role.ASSISTANT
        for call in message.tool_calls
    }


def tool_name_for(message: Message, names: dict[str, str], *, model: str) -> str:
    call_id = message.tool_call_id or ""
    name = names.get(call_id)
    if name is None:
        raise LLMError(
            ErrorKind.BAD_REQUEST,
            "tool result does not answer an earlier tool call",
            model=model,
        )
    return name


def parse_tool_call(
    call_id: str | None, name: str, raw_arguments: object, *, model: str, index: int
) -> ToolCall:
    """Validate a provider's tool call; malformed ones become BAD_TOOL_CALL."""
    arguments = raw_arguments
    if isinstance(raw_arguments, str):
        try:
            arguments = json.loads(raw_arguments) if raw_arguments.strip() else {}
        except ValueError:
            raise LLMError(
                ErrorKind.BAD_TOOL_CALL, f"tool call {name!r} has invalid JSON", model=model
            ) from None
    if not isinstance(arguments, dict):
        raise LLMError(
            ErrorKind.BAD_TOOL_CALL, f"tool call {name!r} arguments are not an object", model=model
        )
    try:
        return ToolCall(id=call_id or f"call_{index}", name=name, arguments=arguments)
    except ValidationError:
        raise LLMError(
            ErrorKind.BAD_TOOL_CALL, f"tool call {name!r} is not a valid call", model=model
        ) from None


def unmapped(exc: BaseException, *, model: str) -> LLMError:
    """Last-resort mapping. The original is logged without its message, which may echo prompts."""
    logger.warning("unmapped provider error %s from %s", type(exc).__name__, model)
    logger.debug("unmapped provider error detail", exc_info=exc)
    return LLMError(ErrorKind.PROVIDER_DOWN, f"unexpected {type(exc).__name__}", model=model)
