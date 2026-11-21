"""Provider-agnostic chat model module. Application code imports only from this package root."""

from cardwise_llm.config import (
    ChainEntry,
    LLMConfig,
    LLMConfigError,
    build_chat_model,
    load_llm_config,
)
from cardwise_llm.errors import ErrorKind, LLMError
from cardwise_llm.fake import FakeChatModel, FakeTurn
from cardwise_llm.port import ChatModel, complete
from cardwise_llm.quota import InMemoryQuotaStore, QuotaLimits, QuotaStore
from cardwise_llm.resilient import ChainLink, ResilientModel, RetryPolicy
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
    "ChainEntry",
    "ChainLink",
    "ChatModel",
    "ErrorKind",
    "FakeChatModel",
    "FakeTurn",
    "FinishReason",
    "Finished",
    "InMemoryQuotaStore",
    "LLMConfig",
    "LLMConfigError",
    "LLMError",
    "LLMEvent",
    "LLMRequest",
    "LLMResponse",
    "Message",
    "QuotaLimits",
    "QuotaStore",
    "ResilientModel",
    "RetryPolicy",
    "Role",
    "TextDelta",
    "ToolCall",
    "ToolCallReady",
    "ToolSpec",
    "Usage",
    "UsageReport",
    "build_chat_model",
    "complete",
    "load_llm_config",
]
