"""Provider-neutral types for one model turn: messages, tools, usage and stream events."""

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class Model(BaseModel):
    """Base for every public type: unknown fields are rejected and instances are immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)


ToolName = Annotated[str, Field(pattern=r"^[a-z_][a-z0-9_]{0,63}$")]


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolCall(Model):
    id: Annotated[str, Field(min_length=1, max_length=128)]
    name: ToolName
    arguments: dict[str, JsonValue]


class Message(Model):
    role: Role
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None

    @model_validator(mode="after")
    def _check_role_fields(self) -> Self:
        if self.tool_calls and self.role is not Role.ASSISTANT:
            raise ValueError("only assistant messages can carry tool calls")
        if (self.role is Role.TOOL) != (self.tool_call_id is not None):
            raise ValueError("tool_call_id is required on tool messages and allowed only there")
        return self

    @classmethod
    def system(cls, content: str) -> Self:
        return cls(role=Role.SYSTEM, content=content)

    @classmethod
    def user(cls, content: str) -> Self:
        return cls(role=Role.USER, content=content)

    @classmethod
    def assistant(cls, content: str = "", tool_calls: tuple[ToolCall, ...] = ()) -> Self:
        return cls(role=Role.ASSISTANT, content=content, tool_calls=tool_calls)

    @classmethod
    def tool_result(cls, tool_call_id: str, content: str) -> Self:
        return cls(role=Role.TOOL, content=content, tool_call_id=tool_call_id)


class ToolSpec(Model):
    name: ToolName
    description: Annotated[str, Field(min_length=1, max_length=1024)]
    parameters: dict[str, JsonValue]
    """JSON Schema for the arguments object."""

    @classmethod
    def from_model(cls, name: str, description: str, arguments: type[BaseModel]) -> Self:
        return cls(name=name, description=description, parameters=arguments.model_json_schema())


class Usage(Model):
    input_tokens: Annotated[int, Field(ge=0)] = 0
    output_tokens: Annotated[int, Field(ge=0)] = 0
    cached_tokens: Annotated[int, Field(ge=0)] = 0
    reasoning_tokens: Annotated[int, Field(ge=0)] = 0
    unmeasured: bool = False
    """True when the provider returned no usage for at least one request."""

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cached_tokens=self.cached_tokens + other.cached_tokens,
            reasoning_tokens=self.reasoning_tokens + other.reasoning_tokens,
            unmeasured=self.unmeasured or other.unmeasured,
        )


class LLMRequest(Model):
    messages: Annotated[tuple[Message, ...], Field(min_length=1)]
    tools: tuple[ToolSpec, ...] = ()
    max_output_tokens: Annotated[int, Field(gt=0, le=8192)] = 1024
    temperature: Annotated[float, Field(ge=0, le=2)] = 0.3
    timeout_s: Annotated[float, Field(gt=0, le=120)] = 45


class TextDelta(Model):
    type: Literal["text"] = "text"
    text: str


class ToolCallReady(Model):
    """A complete tool call. Adapters buffer argument fragments and emit only whole calls."""

    type: Literal["tool_call"] = "tool_call"
    call: ToolCall


class UsageReport(Model):
    type: Literal["usage"] = "usage"
    usage: Usage
    model: str


FinishReason = Literal["stop", "tool_calls", "length", "filtered"]


class Finished(Model):
    type: Literal["finished"] = "finished"
    reason: FinishReason


LLMEvent = Annotated[
    TextDelta | ToolCallReady | UsageReport | Finished, Field(discriminator="type")
]


class LLMResponse(Model):
    """A whole turn, collected from the stream by `complete()`."""

    model: str
    text: str
    tool_calls: tuple[ToolCall, ...]
    usage: Usage
    finish_reason: FinishReason
