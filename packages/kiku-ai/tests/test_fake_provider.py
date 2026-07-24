import asyncio
from datetime import UTC, datetime

from kiku_ai import (
    AssistantMessage,
    AssistantMessageEvent,
    Context,
    DoneEvent,
    ErrorEvent,
    Model,
    StartEvent,
    StopReason,
    StreamOptions,
    TextContent,
    TextDeltaEvent,
    TextEndEvent,
    TextStartEvent,
    ThinkingContent,
    ThinkingDeltaEvent,
    ThinkingEndEvent,
    ThinkingStartEvent,
    ToolCall,
    ToolCallDeltaEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
    ToolResultMessage,
    Usage,
)
from kiku_ai.api import FakeApiAdapter
from kiku_ai.auth import MemoryCredentialStore
from kiku_ai.providers.fake import FakeProvider, FakeProviderState


def make_response(
    text: str,
    stop_reason: StopReason = StopReason.STOP,
    error_message: str | None = None,
) -> AssistantMessage:
    return AssistantMessage(
        timestamp=datetime.now(UTC),
        content=[TextContent(content=text)],
        usage=Usage(input=3, output=2),
        stop_reason=stop_reason,
        error_message=error_message,
    )


async def collect_response(
    provider: FakeProvider,
) -> tuple[list[AssistantMessageEvent], AssistantMessage]:
    model = provider.get_model("fake-model")
    assert model is not None
    events = [event async for event in provider.stream(model, Context(messages=[]))]
    terminal = events[-1]
    if isinstance(terminal, DoneEvent):
        return events, terminal.message
    assert isinstance(terminal, ErrorEvent)
    return events, terminal.error


def test_owns_api_adapter_and_base_url() -> None:
    provider = FakeProvider(credential_store=MemoryCredentialStore())

    assert isinstance(provider.api, FakeApiAdapter)
    assert provider.base_url == "fake://"


async def test_streams_a_scripted_text_response() -> None:
    response = make_response("Hello from the fake provider")
    provider = FakeProvider(
        responses=[response],
        credential_store=MemoryCredentialStore(),
    )

    events, result = await collect_response(provider)

    assert isinstance(events[0], StartEvent)
    assert isinstance(events[-1], DoneEvent)
    assert (
        "".join(event.delta for event in events if isinstance(event, TextDeltaEvent)) == "Hello from the fake provider"
    )
    assert result is response


async def test_consumes_responses_in_order_and_can_enqueue_more() -> None:
    first = make_response("first")
    second = make_response("second")
    third = make_response("third")
    provider = FakeProvider(
        responses=[first, second],
        credential_store=MemoryCredentialStore(),
    )
    provider.enqueue(third)

    assert (await collect_response(provider))[1] is first
    assert (await collect_response(provider))[1] is second
    assert (await collect_response(provider))[1] is third


async def test_empty_response_queue_returns_an_error_event() -> None:
    events, result = await collect_response(FakeProvider(credential_store=MemoryCredentialStore()))

    assert len(events) == 1
    assert isinstance(events[0], ErrorEvent)
    assert result.stop_reason == StopReason.ERROR
    assert result.error_message == "No fake response is queued"


async def test_scripted_error_response_terminates_with_error() -> None:
    response = make_response("partial", StopReason.ERROR, "Provider failed")

    events, result = await collect_response(
        FakeProvider(
            responses=[response],
            credential_store=MemoryCredentialStore(),
        )
    )

    assert isinstance(events[-1], ErrorEvent)
    assert events[-1].reason == StopReason.ERROR
    assert result is response


async def test_scripted_aborted_response_terminates_with_error() -> None:
    response = make_response("partial", StopReason.ABORTED, "Request cancelled")

    events, result = await collect_response(
        FakeProvider(
            responses=[response],
            credential_store=MemoryCredentialStore(),
        )
    )

    assert isinstance(events[-1], ErrorEvent)
    assert events[-1].reason == StopReason.ABORTED
    assert result is response


async def test_event_order_is_deterministic() -> None:
    provider = FakeProvider(
        responses=[make_response("0123456789")],
        credential_store=MemoryCredentialStore(),
    )

    events, _ = await collect_response(provider)

    assert [event.type for event in events] == [
        "start",
        "text_start",
        "text_delta",
        "text_delta",
        "text_end",
        "done",
    ]
    assert [event.delta for event in events if isinstance(event, TextDeltaEvent)] == ["01234567", "89"]


async def test_streams_mixed_thinking_text_and_tool_call_content() -> None:
    tool_call = ToolCall(
        id="call-1",
        name="read",
        arguments={"path": "README.md", "line": 3},
    )
    response = AssistantMessage(
        timestamp=datetime.now(UTC),
        content=[
            ThinkingContent(thinking="Inspect the file", thinking_signature="signature"),
            TextContent(content="I'll inspect it."),
            tool_call,
        ],
        usage=Usage(input=3, output=8, reasoning=2),
        stop_reason=StopReason.TOOL_USE,
    )
    provider = FakeProvider(
        responses=[response],
        credential_store=MemoryCredentialStore(),
    )

    events, result = await collect_response(provider)

    assert [event.type for event in events] == [
        "start",
        "thinking_start",
        "thinking_delta",
        "thinking_delta",
        "thinking_end",
        "text_start",
        "text_delta",
        "text_delta",
        "text_end",
        "tool_call_start",
        "tool_call_delta",
        "tool_call_delta",
        "tool_call_delta",
        "tool_call_delta",
        "tool_call_end",
        "done",
    ]
    assert "".join(
        event.delta for event in events if isinstance(event, ThinkingDeltaEvent)
    ) == "Inspect the file"
    assert "".join(
        event.delta for event in events if isinstance(event, ToolCallDeltaEvent)
    ) == '{"path":"README.md","line":3}'
    assert any(isinstance(event, ThinkingStartEvent) for event in events)
    assert any(isinstance(event, ThinkingEndEvent) for event in events)
    assert any(isinstance(event, TextStartEvent) for event in events)
    assert any(isinstance(event, TextEndEvent) for event in events)
    assert any(isinstance(event, ToolCallStartEvent) for event in events)
    tool_end = next(event for event in events if isinstance(event, ToolCallEndEvent))
    assert tool_end.tool_call == tool_call
    assert tool_end.partial.content == response.content
    assert result is response


async def test_scripted_tool_turn_can_be_followed_with_accumulated_context() -> None:
    first = AssistantMessage(
        timestamp=datetime.now(UTC),
        content=[ToolCall(id="call-1", name="read", arguments={"path": "README.md"})],
        usage=Usage(input=1, output=1),
        stop_reason=StopReason.TOOL_USE,
    )
    tool_result = ToolResultMessage(
        timestamp=datetime.now(UTC),
        tool_call_id="call-1",
        tool_name="read",
        content=[TextContent(content="file contents")],
        is_error=False,
    )

    def second_factory(
        context: Context,
        options: StreamOptions | None,
        state: FakeProviderState,
        model: Model,
    ) -> AssistantMessage:
        del options, state, model
        assert context.messages == [first, tool_result]
        return make_response("finished")

    provider = FakeProvider(
        responses=[first, second_factory],
        credential_store=MemoryCredentialStore(),
    )
    model = provider.get_model("fake-model")
    assert model is not None

    first_events = [event async for event in provider.stream(model, Context(messages=[]))]
    tool_end = next(event for event in first_events if isinstance(event, ToolCallEndEvent))
    assert tool_end.tool_call.arguments == {"path": "README.md"}

    second_events = [
        event
        async for event in provider.stream(
            model,
            Context(messages=[first, tool_result]),
        )
    ]
    terminal = second_events[-1]
    assert isinstance(terminal, DoneEvent)
    assert terminal.message.content == [TextContent(content="finished")]


async def test_response_factory_receives_request_and_state() -> None:
    def factory(
        context: Context,
        options: StreamOptions | None,
        state: FakeProviderState,
        model: Model,
    ) -> AssistantMessage:
        assert options is not None
        return make_response(f"{len(context.messages)}:{options.session_id}:{state.call_count}:{model.id}")

    provider = FakeProvider(
        responses=[factory],
        credential_store=MemoryCredentialStore(),
    )
    model = provider.get_model("fake-model")
    assert model is not None

    events = [
        event
        async for event in provider.stream(
            model,
            Context(messages=[]),
            StreamOptions(session_id="session-1"),
        )
    ]
    terminal = events[-1]
    assert isinstance(terminal, DoneEvent)
    assert terminal.message.content == [TextContent(content="0:session-1:1:fake-model")]
    assert provider.state.call_count == 1


async def test_async_response_factory() -> None:
    async def factory(
        context: Context,
        options: StreamOptions | None,
        state: FakeProviderState,
        model: Model,
    ) -> AssistantMessage:
        del context, options, state, model
        await asyncio.sleep(0)
        return make_response("async response")

    events, result = await collect_response(
        FakeProvider(
            responses=[factory],
            credential_store=MemoryCredentialStore(),
        )
    )

    assert isinstance(events[-1], DoneEvent)
    assert result.content == [TextContent(content="async response")]


async def test_response_factory_exception_becomes_stream_error() -> None:
    def factory(
        context: Context,
        options: StreamOptions | None,
        state: FakeProviderState,
        model: Model,
    ) -> AssistantMessage:
        del context, options, state, model
        raise RuntimeError("boom")

    events, result = await collect_response(
        FakeProvider(
            responses=[factory],
            credential_store=MemoryCredentialStore(),
        )
    )

    assert len(events) == 1
    assert isinstance(events[0], ErrorEvent)
    assert result.stop_reason == StopReason.ERROR
    assert result.error_message == "boom"
