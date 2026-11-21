"""One chat turn: the stream the message route returns once the limits and the chat check pass.

The route has already saved the user's message and taken a stream slot. This generator runs
the agent, forwards its events, saves the assistant message and releases the slot. Whatever
ends the stream (done, model failure, a bug, or the client going away) the reply is saved with
a matching status and the slot is released.
"""

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Final
from uuid import UUID, uuid4

import anyio

from cardwise_api.agent.port import Agent, AgentEvent, AgentRequest, AgentUsage
from cardwise_api.chats.repository import AssistantReply, ChatRepository, MessageStatus
from cardwise_api.models import CardRef, MessageOut
from cardwise_api.ratelimit import RateLimiter, StreamLease
from cardwise_api.stream_events import (
    CardsEvent,
    DoneEvent,
    ErrorEvent,
    StartEvent,
    StreamEvent,
    TextEvent,
    UsageOut,
)
from cardwise_llm import LLMError

HISTORY_LIMIT: Final = 20
"""Earlier messages passed to the agent as context."""

CLEANUP_TIMEOUT_S: Final = 10.0

log: Final = logging.getLogger("cardwise_api.chats")


@dataclass(frozen=True, slots=True)
class Turn:
    user_id: UUID
    chat_id: UUID
    history: list[MessageOut]
    question: str
    agent: Agent
    repo: ChatRepository
    limiter: RateLimiter
    lease: StreamLease
    request_id: str


@dataclass
class _Reply:
    id: UUID
    text: list[str]
    cards: list[CardRef]
    usage: AgentUsage | None = None
    saved: bool = False

    def build(self, status: MessageStatus) -> AssistantReply:
        return AssistantReply(
            id=self.id,
            content="".join(self.text),
            status=status,
            model=self.usage.model if self.usage else None,
            input_tokens=self.usage.input_tokens if self.usage else 0,
            output_tokens=self.usage.output_tokens if self.usage else 0,
            cards=tuple(self.cards),
        )


async def run_turn(turn: Turn) -> AsyncIterator[StreamEvent]:
    reply = _Reply(id=uuid4(), text=[], cards=[])
    status: MessageStatus = "interrupted"
    agent_events = turn.agent.answer(
        AgentRequest(chat_id=turn.chat_id, history=turn.history, question=turn.question)
    )
    try:
        yield StartEvent(message_id=reply.id)
        try:
            async for event in agent_events:
                forwarded = _record(reply, event)
                if forwarded is not None:
                    yield forwarded
        except LLMError as exc:
            status = "failed"
            log.warning(
                "model failed", extra={"fields": {"kind": str(exc.kind), "model": exc.model}}
            )
            yield ErrorEvent(code="model_unavailable", request_id=turn.request_id)
            return
        except Exception as exc:
            status = "failed"
            log.error("agent failed", exc_info=exc)
            yield ErrorEvent(code="internal", request_id=turn.request_id)
            return
        status = "complete"
        try:
            await _save(turn, reply, status)
        except Exception as exc:
            log.error("saving the reply failed", exc_info=exc)
            yield ErrorEvent(code="internal", request_id=turn.request_id)
            return
        usage = reply.usage or AgentUsage(model="unknown")
        yield DoneEvent(
            message_id=reply.id,
            usage=UsageOut(input_tokens=usage.input_tokens, output_tokens=usage.output_tokens),
        )
    finally:
        # Shielded with a deadline: this also runs after a disconnect cancelled the request.
        with anyio.move_on_after(CLEANUP_TIMEOUT_S, shield=True):
            await _close(agent_events)
            if not reply.saved:
                try:
                    await _save(turn, reply, status)
                except Exception as exc:
                    log.error("saving the reply failed", exc_info=exc)
            try:
                await turn.limiter.release_stream(turn.lease)
            except Exception as exc:
                log.error("releasing the stream slot failed", exc_info=exc)
        log.info(
            "turn finished",
            extra={
                "fields": {
                    "status": status,
                    "model": reply.usage.model if reply.usage else None,
                    "input_tokens": reply.usage.input_tokens if reply.usage else 0,
                    "output_tokens": reply.usage.output_tokens if reply.usage else 0,
                    "cards": len(reply.cards),
                }
            },
        )


def _record(reply: _Reply, event: AgentEvent) -> StreamEvent | None:
    """Keeps what the saved message needs; returns the event to forward, if any."""
    if isinstance(event, AgentUsage):
        reply.usage = event
        return None
    if isinstance(event, TextEvent):
        reply.text.append(event.text)
    elif isinstance(event, CardsEvent):
        reply.cards = list(event.cards)
    return event


async def _save(turn: Turn, reply: _Reply, status: MessageStatus) -> None:
    reply.saved = True
    await turn.repo.add_assistant_message(turn.user_id, turn.chat_id, reply.build(status))


async def _close(events: AsyncIterator[AgentEvent]) -> None:
    aclose = getattr(events, "aclose", None)
    if aclose is None:
        return
    try:
        await aclose()
    except Exception as exc:
        log.error("closing the agent failed", exc_info=exc)
