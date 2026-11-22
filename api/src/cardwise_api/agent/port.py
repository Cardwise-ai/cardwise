"""What the message route needs from the agent (agent.loop.ChatAgent implements it).

The agent answers one user message. It yields text, tool progress and the grounded card list
as stream events, and finally an AgentUsage. The route owns everything around it: the
`start`/`done`/`error` events, persistence, rate limits and disconnects.
"""

from collections.abc import AsyncIterator, Callable, Sequence
from typing import Protocol
from uuid import UUID

from cardwise_api.models import MessageOut, Model
from cardwise_api.retrieval.port import CardBackend
from cardwise_api.stream_events import CardsEvent, TextEvent, ToolEvent
from cardwise_llm import ChatModel


class AgentUsage(Model):
    model: str
    input_tokens: int = 0
    output_tokens: int = 0


class AgentRequest(Model):
    chat_id: UUID
    history: Sequence[MessageOut]
    """Earlier messages in the chat, oldest first, without the new one."""
    question: str


AgentEvent = TextEvent | ToolEvent | CardsEvent | AgentUsage


class Agent(Protocol):
    def answer(self, request: AgentRequest) -> AsyncIterator[AgentEvent]:
        """Raise cardwise_llm.LLMError when the model fails; anything else is a bug."""
        ...


AgentFactory = Callable[[ChatModel, CardBackend], Agent]
"""Builds the agent for one request from the configured model and that request's backend."""
