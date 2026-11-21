"""Provider-agnostic chat model module. Application code imports only from this package root."""

from cardwise_llm.errors import ErrorKind, LLMError
from cardwise_llm.fake import FakeChatModel, FakeTurn
from cardwise_llm.port import ChatModel, complete
from cardwise_llm.types import (
    Finished,
    FinishReason,
    LLMEvent,
    LLMRequest,
    LLMResponse,
    Message,
    Role,
    TextDelta,
    ToolCall,
    ToolCallReady,
    ToolSpec,
    Usage,
    UsageReport,
)

__all__ = [
    "ChatModel",
    "ErrorKind",
    "FakeChatModel",
    "FakeTurn",
    "FinishReason",
    "Finished",
    "LLMError",
    "LLMEvent",
    "LLMRequest",
    "LLMResponse",
    "Message",
    "Role",
    "TextDelta",
    "ToolCall",
    "ToolCallReady",
    "ToolSpec",
    "Usage",
    "UsageReport",
    "complete",
]
