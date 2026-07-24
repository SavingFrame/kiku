import json
from datetime import UTC, datetime

from kiku_ai import (
    AssistantMessage,
    Context,
    ImageContent,
    Model,
    ReasoningLevel,
    StopReason,
    StreamOptions,
    TextContent,
    ThinkingContent,
    Tool,
    ToolCall,
    ToolResultMessage,
    Usage,
    UserMessage,
)
from kiku_ai.api.openai_codex_responses import _build_request as build_openai_codex_request

_TIMESTAMP = datetime(2026, 1, 1, tzinfo=UTC)


def _model() -> Model:
    return Model(
        id="gpt-5.3-codex",
        name="GPT-5.3 Codex",
        provider="openai-codex",
        api="openai-codex-responses",
        context_model=128_000,
        max_output_tokens=32_000,
    )


def test_builds_codex_request_defaults_and_system_instructions() -> None:
    request = build_openai_codex_request(
        _model(),
        Context(
            system_prompt="Follow the repository instructions.",
            messages=[UserMessage(timestamp=_TIMESTAMP, content="Inspect the project.")],
        ),
    )

    assert request == {
        "model": "gpt-5.3-codex",
        "store": False,
        "stream": True,
        "instructions": "Follow the repository instructions.",
        "input": [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": "Inspect the project."}],
            }
        ],
        "text": {"verbosity": "low"},
        "include": ["reasoning.encrypted_content"],
        "tool_choice": "auto",
        "parallel_tool_calls": True,
    }


def test_uses_default_instructions_when_system_prompt_is_absent() -> None:
    request = build_openai_codex_request(_model(), Context(messages=[]))

    assert request["instructions"] == "You are a helpful assistant."


def test_converts_multimodal_user_content() -> None:
    context = Context(
        messages=[
            UserMessage(
                timestamp=_TIMESTAMP,
                content=[
                    TextContent(content="What is shown?"),
                    ImageContent(content="aW1hZ2U=", mime_type="image/png"),
                ],
            )
        ]
    )

    request = build_openai_codex_request(_model(), context)

    assert request["input"] == [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "What is shown?"},
                {
                    "type": "input_image",
                    "detail": "auto",
                    "image_url": "data:image/png;base64,aW1hZ2U=",
                },
            ],
        }
    ]


def test_replays_assistant_text_reasoning_and_tool_calls() -> None:
    reasoning = {
        "type": "reasoning",
        "id": "rs_123",
        "encrypted_content": "encrypted",
        "summary": [],
    }
    context = Context(
        messages=[
            AssistantMessage(
                timestamp=_TIMESTAMP,
                content=[
                    ThinkingContent(thinking="internal", thinking_signature=json.dumps(reasoning)),
                    TextContent(content="I will inspect it."),
                    ToolCall(id="call_123|fc_123", name="read_file", arguments={"path": "README.md"}),
                ],
                usage=Usage(),
                stop_reason=StopReason.TOOL_USE,
            )
        ]
    )

    request = build_openai_codex_request(_model(), context)

    assert request["input"] == [
        reasoning,
        {
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "output_text",
                    "text": "I will inspect it.",
                    "annotations": [],
                }
            ],
            "status": "completed",
            "id": "msg_kiku_0",
        },
        {
            "type": "function_call",
            "id": "fc_123",
            "call_id": "call_123",
            "name": "read_file",
            "arguments": '{"path":"README.md"}',
        },
    ]


def test_replays_tool_results() -> None:
    context = Context(
        messages=[
            ToolResultMessage(
                timestamp=_TIMESTAMP,
                tool_call_id="call_123|fc_123",
                tool_name="read_file",
                content=[TextContent(content="first"), TextContent(content="second")],
                is_error=False,
            ),
            ToolResultMessage(
                timestamp=_TIMESTAMP,
                tool_call_id="call_456",
                tool_name="screenshot",
                content=[ImageContent(content="cG5n", mime_type="image/png")],
                is_error=False,
            ),
        ]
    )

    request = build_openai_codex_request(_model(), context)

    assert request["input"] == [
        {
            "type": "function_call_output",
            "call_id": "call_123",
            "output": "first\nsecond",
        },
        {
            "type": "function_call_output",
            "call_id": "call_456",
            "output": [
                {
                    "type": "input_image",
                    "detail": "auto",
                    "image_url": "data:image/png;base64,cG5n",
                }
            ],
        },
    ]


def test_converts_tools_to_codex_function_declarations() -> None:
    context = Context(
        messages=[],
        tools=[
            Tool(
                name="read_file",
                description="Read a file from the repository.",
                parameters={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            )
        ],
    )

    request = build_openai_codex_request(_model(), context)

    assert request["tools"] == [
        {
            "type": "function",
            "name": "read_file",
            "description": "Read a file from the repository.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            "strict": None,
        }
    ]


def test_converts_codex_stream_options() -> None:
    options = StreamOptions(
        temperature=0.25,
        max_output_tokens=4096,
        reasoning=ReasoningLevel.HIGH,
        session_id="session-123",
    )

    request = build_openai_codex_request(_model(), Context(messages=[]), options)

    assert request["temperature"] == 0.25
    assert request["max_output_tokens"] == 4096
    assert request["reasoning"] == {"effort": "high", "summary": "auto"}
    assert request["prompt_cache_key"] == "session-123"


def test_omits_reasoning_when_explicitly_off() -> None:
    request = build_openai_codex_request(
        _model(),
        Context(messages=[]),
        StreamOptions(reasoning=ReasoningLevel.OFF),
    )

    assert "reasoning" not in request
