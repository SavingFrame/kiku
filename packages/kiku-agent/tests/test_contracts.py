from datetime import UTC, datetime
from typing import Any

import pytest
from jsonschema.exceptions import SchemaError
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from kiku_agent import (
    AgentEndEvent,
    AgentEvent,
    AgentStartEvent,
    AgentTool,
    AgentToolResult,
    MessageEndEvent,
    MessageStartEvent,
    MessageUpdateEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
    TurnEndEvent,
    TurnStartEvent,
    validate_tool_arguments,
)
from kiku_ai import (
    AssistantMessage,
    Context,
    DoneEvent,
    ImageContent,
    StopReason,
    TextContent,
    TextDeltaEvent,
    ToolResultMessage,
    Usage,
    UserMessage,
)
from pydantic import TypeAdapter, ValidationError


class EchoTool(AgentTool):
    name: str = "echo"
    description: str = "Echo text"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
        "additionalProperties": False,
    }

    async def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any],
    ) -> AgentToolResult:
        return AgentToolResult(
            content=[TextContent(content=f"{tool_call_id}:{arguments['text']}")],
            details={"arguments": arguments},
        )


def make_assistant_message() -> AssistantMessage:
    return AssistantMessage(
        timestamp=datetime.now(UTC),
        content=[TextContent(content="hello")],
        usage=Usage(input=1, output=1),
        stop_reason=StopReason.STOP,
    )


def test_constructs_tool_result() -> None:
    result = AgentToolResult(
        content=[
            TextContent(content="done"),
            ImageContent(content="aW1hZ2U=", mime_type="image/png"),
        ],
        details={"path": "image.png"},
    )

    assert result.content[0] == TextContent(content="done")
    assert result.details == {"path": "image.png"}


async def test_agent_tool_is_model_visible_and_executable() -> None:
    tool = EchoTool()
    context = Context(messages=[], tools=[tool])

    assert context.tools == [tool]
    assert tool.model_dump() == {
        "name": "echo",
        "description": "Echo text",
        "parameters": EchoTool.model_fields["parameters"].default,
    }
    assert "execute" not in tool.model_dump()
    assert await tool.execute("call-1", {"text": "hi"}) == AgentToolResult(
        content=[TextContent(content="call-1:hi")],
        details={"arguments": {"text": "hi"}},
    )


def test_validates_tool_arguments_with_json_schema() -> None:
    tool = EchoTool()

    validate_tool_arguments(tool, {"text": "hello"})

    with pytest.raises(JsonSchemaValidationError):
        validate_tool_arguments(tool, {"text": 3})
    with pytest.raises(JsonSchemaValidationError):
        validate_tool_arguments(tool, {})
    with pytest.raises(JsonSchemaValidationError):
        validate_tool_arguments(tool, {"text": "hello", "extra": True})


def test_rejects_an_invalid_tool_schema() -> None:
    tool = EchoTool(parameters={"type": "not-a-json-schema-type"})

    with pytest.raises(SchemaError):
        validate_tool_arguments(tool, {"text": "hello"})


def test_constructs_and_round_trips_every_event_variant() -> None:
    assistant = make_assistant_message()
    user = UserMessage(timestamp=datetime.now(UTC), content="go")
    tool_message = ToolResultMessage(
        timestamp=datetime.now(UTC),
        tool_call_id="call-1",
        tool_name="echo",
        content=[TextContent(content="done")],
        is_error=False,
    )
    result = AgentToolResult(content=[TextContent(content="done")], details={"elapsed": 0.1})
    source = TextDeltaEvent(content_index=0, delta="hello", partial=assistant)
    events: list[AgentEvent] = [
        AgentStartEvent(),
        AgentEndEvent(messages=[user, assistant, tool_message]),
        TurnStartEvent(),
        TurnEndEvent(message=assistant, tool_results=[tool_message]),
        MessageStartEvent(message=user),
        MessageUpdateEvent(message=assistant, assistant_message_event=source),
        MessageEndEvent(message=tool_message),
        ToolExecutionStartEvent(
            tool_call_id="call-1",
            tool_name="echo",
            arguments={"text": "hello"},
        ),
        ToolExecutionEndEvent(
            tool_call_id="call-1",
            tool_name="echo",
            result=result,
            is_error=False,
        ),
    ]
    adapter = TypeAdapter(AgentEvent)

    round_tripped = [adapter.validate_json(adapter.dump_json(event)) for event in events]

    assert round_tripped == events
    assert [event.type for event in round_tripped] == [
        "agent_start",
        "agent_end",
        "turn_start",
        "turn_end",
        "message_start",
        "message_update",
        "message_end",
        "tool_execution_start",
        "tool_execution_end",
    ]


def test_message_update_accepts_terminal_assistant_source_event() -> None:
    assistant = make_assistant_message()
    event = MessageUpdateEvent(
        message=assistant,
        assistant_message_event=DoneEvent(reason=StopReason.STOP, message=assistant),
    )

    assert event.assistant_message_event.type == "done"


def test_rejects_malformed_event_discriminators() -> None:
    adapter = TypeAdapter(AgentEvent)

    with pytest.raises(ValidationError):
        adapter.validate_python({"type": "agent_started"})
    with pytest.raises(ValidationError):
        adapter.validate_python({"messages": []})
