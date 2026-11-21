import pytest

from cardwise_llm import (
    ErrorKind,
    FakeChatModel,
    Finished,
    LLMError,
    LLMRequest,
    Message,
    TextDelta,
    ToolCall,
    Usage,
    UsageReport,
    complete,
)

REQUEST = LLMRequest(messages=(Message.user("cards like Craterhoof Behemoth"),))


async def test_complete_collects_text_tool_calls_and_usage() -> None:
    call = ToolCall(id="c1", name="search_cards", arguments={"text": "overrun"})
    model = FakeChatModel(
        [
            [
                TextDelta(text="Looking"),
                TextDelta(text=" up cards."),
                *FakeChatModel.tool_turn(call),
            ]
        ]
    )

    response = await complete(model, REQUEST)

    assert response.text == "Looking up cards."
    assert response.tool_calls == (call,)
    assert response.finish_reason == "tool_calls"
    assert response.usage == Usage(input_tokens=10, output_tokens=5)
    assert model.requests == [REQUEST]


async def test_complete_marks_usage_unmeasured_when_provider_reports_none() -> None:
    model = FakeChatModel([[TextDelta(text="hi"), Finished(reason="stop")]])
    assert (await complete(model, REQUEST)).usage.unmeasured


async def test_stream_without_finish_is_a_provider_error() -> None:
    model = FakeChatModel([[TextDelta(text="partial")]])
    with pytest.raises(LLMError) as raised:
        await complete(model, REQUEST)
    assert raised.value.kind is ErrorKind.PROVIDER_DOWN


async def test_events_after_finish_are_rejected() -> None:
    usage = UsageReport(usage=Usage(), model="fake:scripted")
    model = FakeChatModel([[Finished(reason="stop"), usage]])
    with pytest.raises(LLMError, match="after finish"):
        await complete(model, REQUEST)


async def test_scripted_errors_are_raised_mid_stream() -> None:
    error = LLMError(ErrorKind.RATE_LIMIT, "slow down", model="fake:scripted", retry_after_s=2)
    model = FakeChatModel([[TextDelta(text="par"), error]])
    with pytest.raises(LLMError) as raised:
        await complete(model, REQUEST)
    assert raised.value.retryable
    assert raised.value.retry_after_s == 2


def test_error_kinds_split_into_retry_and_fallback() -> None:
    quota = LLMError(ErrorKind.QUOTA_EXHAUSTED, "daily cap", model="m")
    auth = LLMError(ErrorKind.AUTH, "bad key", model="m")
    assert not quota.retryable
    assert quota.allows_fallback
    assert not auth.retryable
    assert not auth.allows_fallback
