import asyncio
import json
from collections.abc import AsyncIterator, Sequence

import httpx
import pytest
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
    ThinkingContent,
    ToolCall,
    UserMessage,
)
from kiku_ai.api import ApiAdapter, OpenAICodexResponsesAdapter
from kiku_ai.auth import ModelAuth


def _model() -> Model:
    return Model(
        id="gpt-5.3-codex",
        name="GPT-5.3 Codex",
        provider="openai-codex",
        api="openai-codex-responses",
        context_model=128_000,
        max_output_tokens=32_000,
    )


def _auth() -> ModelAuth:
    return ModelAuth(api_key="token", headers={"chatgpt-account-id": "account-123"})


def _sse(events: Sequence[dict[str, object]]) -> bytes:
    return "".join(f"data: {json.dumps(event)}\n\n" for event in events).encode()


def _terminal_message(events: Sequence[AssistantMessageEvent]) -> AssistantMessage:
    terminal = events[-1]
    if isinstance(terminal, DoneEvent):
        return terminal.message
    assert isinstance(terminal, ErrorEvent)
    return terminal.error


async def _collect(stream: AsyncIterator[AssistantMessageEvent]) -> list[AssistantMessageEvent]:
    return [event async for event in stream]


async def test_adapter_posts_codex_request_and_streams_text() -> None:
    captured_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse(
                [
                    {
                        "type": "response.created",
                        "response": {"id": "resp_123"},
                    },
                    {
                        "type": "response.output_item.added",
                        "output_index": 0,
                        "item": {"type": "message", "id": "msg_123", "content": []},
                    },
                    {
                        "type": "response.output_text.delta",
                        "output_index": 0,
                        "delta": "Hello",
                    },
                    {
                        "type": "response.output_item.done",
                        "output_index": 0,
                        "item": {
                            "type": "message",
                            "id": "msg_123",
                            "content": [{"type": "output_text", "text": "Hello"}],
                        },
                    },
                    {
                        "type": "response.completed",
                        "response": {
                            "id": "resp_123",
                            "status": "completed",
                            "usage": {
                                "input_tokens": 7,
                                "output_tokens": 2,
                                "input_tokens_details": {"cached_tokens": 3},
                            },
                        },
                    },
                ]
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter: ApiAdapter = OpenAICodexResponsesAdapter(client)
        context = Context(messages=[UserMessage(timestamp="2026-01-01T00:00:00Z", content="Hello")])
        stream = adapter.stream(
            _model(),
            context,
            StreamOptions(
                session_id="session-123",
                headers={
                    "x-kiku-test": "yes",
                    "originator": "wrong",
                    "chatgpt-account-id": "wrong",
                    "authorization": "Bearer wrong",
                },
            ),
            auth=_auth(),
            base_url="https://chatgpt.example/backend-api/",
        )
        assert captured_request is None
        events = [event async for event in stream]
        result = _terminal_message(events)

    assert captured_request is not None
    assert captured_request.url == "https://chatgpt.example/backend-api/codex/responses"
    assert captured_request.headers["authorization"] == "Bearer token"
    assert captured_request.headers["chatgpt-account-id"] == "account-123"
    assert captured_request.headers["openai-beta"] == "responses=experimental"
    assert captured_request.headers["accept"] == "text/event-stream"
    assert captured_request.headers["content-type"] == "application/json"
    assert captured_request.headers["originator"] == "kiku"
    assert captured_request.headers["user-agent"] == "kiku-ai/0.1.0"
    assert captured_request.headers["session-id"] == "session-123"
    assert captured_request.headers["x-client-request-id"] == "session-123"
    assert captured_request.headers["x-kiku-test"] == "yes"
    assert json.loads(captured_request.content)["model"] == "gpt-5.3-codex"

    assert [event.type for event in events] == ["start", "text_start", "text_delta", "text_end", "done"]
    assert isinstance(events[0], StartEvent)
    assert events[0].partial.stop_reason is None
    assert isinstance(events[2], TextDeltaEvent)
    assert events[2].partial.stop_reason is None
    assert result.content == [TextContent(content="Hello")]
    assert result.response_id == "resp_123"
    assert result.stop_reason == StopReason.STOP
    assert result.usage.input == 4
    assert result.usage.cache_read == 3
    assert result.usage.output == 2


async def test_completes_when_terminal_event_arrives_before_body_closes() -> None:
    class OpenBody(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield _sse(
                [
                    {
                        "type": "response.completed",
                        "response": {"id": "resp_123", "status": "completed"},
                    }
                ]
            )
            await asyncio.Event().wait()

        async def aclose(self) -> None:
            self.closed = True

    body = OpenBody()

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, stream=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = OpenAICodexResponsesAdapter(client)
        stream = adapter.stream(_model(), Context(messages=[]), auth=_auth(), base_url="https://example.test")
        events = await asyncio.wait_for(_collect(stream), timeout=0.5)

    assert [event.type for event in events] == ["start", "done"]
    assert _terminal_message(events).stop_reason == StopReason.STOP
    assert body.closed


async def test_maps_incomplete_response_to_length() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            content=_sse(
                [
                    {
                        "type": "response.incomplete",
                        "response": {
                            "id": "resp_incomplete",
                            "status": "incomplete",
                            "incomplete_details": {"reason": "max_output_tokens"},
                            "usage": {
                                "input_tokens": 30,
                                "output_tokens": 12,
                                "input_tokens_details": {
                                    "cached_tokens": 5,
                                    "cache_write_tokens": 3,
                                },
                            },
                        },
                    }
                ]
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = OpenAICodexResponsesAdapter(client)
        events = [
            event
            async for event in adapter.stream(
                _model(), Context(messages=[]), auth=_auth(), base_url="https://example.test"
            )
        ]

    result = _terminal_message(events)
    assert result.stop_reason == StopReason.LENGTH
    assert result.response_id == "resp_incomplete"
    assert result.usage.input == 22
    assert result.usage.cache_read == 5
    assert result.usage.cache_write == 3


async def test_failed_response_preserves_provider_code_and_message() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            content=_sse(
                [
                    {
                        "type": "response.failed",
                        "response": {
                            "id": "resp_failed",
                            "status": "failed",
                            "error": {"code": "server_error", "message": "boom"},
                        },
                    }
                ]
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = OpenAICodexResponsesAdapter(client)
        events = [
            event
            async for event in adapter.stream(
                _model(), Context(messages=[]), auth=_auth(), base_url="https://example.test"
            )
        ]

    result = _terminal_message(events)
    assert result.stop_reason == StopReason.ERROR
    assert result.error_message == "server_error: boom"


async def test_clamps_session_affinity_values_to_64_characters() -> None:
    captured_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(
            200,
            content=_sse([{"type": "response.completed", "response": {"status": "completed"}}]),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = OpenAICodexResponsesAdapter(client)
        events = [
            event
            async for event in adapter.stream(
                _model(),
                Context(messages=[]),
                StreamOptions(session_id="x" * 67),
                auth=_auth(),
                base_url="https://example.test",
            )
        ]

    assert isinstance(events[-1], DoneEvent)
    assert captured_request is not None
    assert captured_request.headers["session-id"] == "x" * 64
    assert captured_request.headers["x-client-request-id"] == "x" * 64
    assert json.loads(captured_request.content)["prompt_cache_key"] == "x" * 64


async def test_streams_reasoning_and_tool_calls() -> None:
    reasoning_item = {
        "type": "reasoning",
        "id": "rs_123",
        "summary": [{"type": "summary_text", "text": "Inspecting"}],
        "encrypted_content": "encrypted",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            content=_sse(
                [
                    {
                        "type": "response.output_item.added",
                        "output_index": 0,
                        "item": {"type": "reasoning", "id": "rs_123", "summary": []},
                    },
                    {
                        "type": "response.reasoning_summary_text.delta",
                        "output_index": 0,
                        "delta": "Inspecting",
                    },
                    {
                        "type": "response.output_item.done",
                        "output_index": 0,
                        "item": reasoning_item,
                    },
                    {
                        "type": "response.output_item.added",
                        "output_index": 1,
                        "item": {
                            "type": "function_call",
                            "id": "fc_123",
                            "call_id": "call_123",
                            "name": "read_file",
                            "arguments": "",
                        },
                    },
                    {
                        "type": "response.function_call_arguments.delta",
                        "output_index": 1,
                        "delta": '{"path":"README',
                    },
                    {
                        "type": "response.function_call_arguments.done",
                        "output_index": 1,
                        "arguments": '{"path":"README.md"}',
                    },
                    {
                        "type": "response.output_item.done",
                        "output_index": 1,
                        "item": {
                            "type": "function_call",
                            "id": "fc_123",
                            "call_id": "call_123",
                            "name": "read_file",
                            "arguments": '{"path":"README.md"}',
                        },
                    },
                    {
                        "type": "response.completed",
                        "response": {
                            "status": "completed",
                            "usage": {
                                "input_tokens": 10,
                                "output_tokens": 8,
                                "output_tokens_details": {"reasoning_tokens": 4},
                            },
                        },
                    },
                ]
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = OpenAICodexResponsesAdapter(client)
        stream = adapter.stream(_model(), Context(messages=[]), auth=_auth(), base_url="https://example.test")
        events = [event async for event in stream]
        result = _terminal_message(events)

    assert [event.type for event in events] == [
        "start",
        "thinking_start",
        "thinking_delta",
        "thinking_end",
        "tool_call_start",
        "tool_call_delta",
        "tool_call_delta",
        "tool_call_end",
        "done",
    ]
    thinking = result.content[0]
    assert isinstance(thinking, ThinkingContent)
    assert thinking.thinking == "Inspecting"
    assert thinking.thinking_signature == json.dumps(reasoning_item, separators=(",", ":"))
    tool_call = result.content[1]
    assert isinstance(tool_call, ToolCall)
    assert tool_call == ToolCall(
        id="call_123|fc_123",
        name="read_file",
        arguments={"path": "README.md"},
    )
    assert result.stop_reason == StopReason.TOOL_USE
    assert result.usage.reasoning == 4


async def test_http_failure_becomes_stream_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(401, text='{"error":"unauthorized"}')

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = OpenAICodexResponsesAdapter(client)
        stream = adapter.stream(_model(), Context(messages=[]), auth=_auth(), base_url="https://example.test")
        events = [event async for event in stream]

    assert [event.type for event in events] == ["start", "error"]
    error = events[-1]
    assert isinstance(error, ErrorEvent)
    assert error.reason == StopReason.ERROR
    assert error.error.error_message is not None
    assert "HTTP 401" in error.error.error_message


async def test_truncated_sse_becomes_stream_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            content=_sse(
                [
                    {
                        "type": "response.output_item.added",
                        "item": {"type": "message", "id": "msg_123", "content": []},
                    },
                    {"type": "response.output_text.delta", "delta": "partial"},
                ]
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = OpenAICodexResponsesAdapter(client)
        stream = adapter.stream(_model(), Context(messages=[]), auth=_auth(), base_url="https://example.test")
        events = [event async for event in stream]
        result = _terminal_message(events)

    assert events[-1].type == "error"
    assert result.stop_reason == StopReason.ERROR
    assert result.content == [TextContent(content="partial")]
    assert result.error_message == "OpenAI Codex stream ended before a terminal response event"


async def test_cancelling_consumer_cancels_http_stream() -> None:
    class BlockingBody(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self) -> AsyncIterator[bytes]:
            await asyncio.Event().wait()
            yield b""

        async def aclose(self) -> None:
            self.closed = True

    body = BlockingBody()

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, stream=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = OpenAICodexResponsesAdapter(client)
        stream = adapter.stream(_model(), Context(messages=[]), auth=_auth(), base_url="https://example.test")
        assert isinstance(await anext(stream), StartEvent)

        async def consume_one() -> AssistantMessageEvent:
            return await anext(stream)

        consumer = asyncio.create_task(consume_one())
        await asyncio.sleep(0)
        consumer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await consumer

    assert body.closed
