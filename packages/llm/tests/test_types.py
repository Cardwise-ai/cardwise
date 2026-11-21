import pytest
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from cardwise_llm import (
    Finished,
    LLMEvent,
    LLMRequest,
    Message,
    Role,
    TextDelta,
    ToolCall,
    ToolCallReady,
    ToolSpec,
    Usage,
)

events = TypeAdapter(LLMEvent)


def test_tool_messages_require_a_call_id() -> None:
    with pytest.raises(ValidationError, match="tool_call_id"):
        Message(role=Role.TOOL, content="result")
    with pytest.raises(ValidationError, match="tool_call_id"):
        Message(role=Role.USER, content="hi", tool_call_id="c1")
    assert Message.tool_result("c1", "result").tool_call_id == "c1"


def test_only_assistant_messages_carry_tool_calls() -> None:
    call = ToolCall(id="c1", name="search_cards", arguments={})
    with pytest.raises(ValidationError, match="only assistant"):
        Message(role=Role.USER, tool_calls=(call,))
    assert Message.assistant(tool_calls=(call,)).tool_calls == (call,)


def test_types_reject_unknown_fields_and_are_immutable() -> None:
    with pytest.raises(ValidationError):
        Message.model_validate({"role": "user", "content": "hi", "name": "x"})
    msg = Message.user("hi")
    with pytest.raises(ValidationError):
        msg.content = "changed"  # type: ignore[misc]


def test_tool_names_are_restricted() -> None:
    with pytest.raises(ValidationError):
        ToolCall(id="c1", name="Search Cards", arguments={})


def test_tool_spec_from_model_uses_the_json_schema() -> None:
    class Args(BaseModel):
        query: str = Field(max_length=200)

    spec = ToolSpec.from_model("search_cards", "Search the card corpus.", Args)
    assert spec.parameters["properties"] == {
        "query": {"maxLength": 200, "title": "Query", "type": "string"}
    }


def test_request_needs_messages_and_bounds_settings() -> None:
    with pytest.raises(ValidationError):
        LLMRequest(messages=())
    with pytest.raises(ValidationError):
        LLMRequest(messages=(Message.user("hi"),), max_output_tokens=0)


def test_events_parse_by_type() -> None:
    assert events.validate_python({"type": "text", "text": "hi"}) == TextDelta(text="hi")
    assert events.validate_python({"type": "finished", "reason": "stop"}) == Finished(reason="stop")
    call = events.validate_python(
        {"type": "tool_call", "call": {"id": "c1", "name": "get_card", "arguments": {"id": "x"}}}
    )
    assert isinstance(call, ToolCallReady)
    with pytest.raises(ValidationError):
        events.validate_python({"type": "image", "url": "https://example.com"})


def test_usage_adds_and_keeps_unmeasured() -> None:
    total = Usage(input_tokens=3, output_tokens=1) + Usage(input_tokens=2, unmeasured=True)
    assert total == Usage(input_tokens=5, output_tokens=1, unmeasured=True)
