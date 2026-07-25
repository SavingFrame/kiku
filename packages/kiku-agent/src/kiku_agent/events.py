from typing import Annotated, Any, Literal

from kiku_ai import (
    AssistantMessage,
    AssistantMessageEvent,
    Message,
    ToolResultMessage,
)
from pydantic import BaseModel, Field

from kiku_agent.tools import AgentToolResult


class AgentStartEvent(BaseModel):
    type: Literal["agent_start"] = "agent_start"


class AgentEndEvent(BaseModel):
    type: Literal["agent_end"] = "agent_end"
    messages: list[Message]


class TurnStartEvent(BaseModel):
    type: Literal["turn_start"] = "turn_start"


class TurnEndEvent(BaseModel):
    type: Literal["turn_end"] = "turn_end"
    message: AssistantMessage
    tool_results: list[ToolResultMessage]


class MessageStartEvent(BaseModel):
    type: Literal["message_start"] = "message_start"
    message: Message


class MessageUpdateEvent(BaseModel):
    type: Literal["message_update"] = "message_update"
    message: Message
    assistant_message_event: AssistantMessageEvent


class MessageEndEvent(BaseModel):
    type: Literal["message_end"] = "message_end"
    message: Message


class ToolExecutionStartEvent(BaseModel):
    type: Literal["tool_execution_start"] = "tool_execution_start"
    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any]


class ToolExecutionEndEvent(BaseModel):
    type: Literal["tool_execution_end"] = "tool_execution_end"
    tool_call_id: str
    tool_name: str
    result: AgentToolResult
    is_error: bool


type AgentEvent = Annotated[
    AgentStartEvent
    | AgentEndEvent
    | TurnStartEvent
    | TurnEndEvent
    | MessageStartEvent
    | MessageUpdateEvent
    | MessageEndEvent
    | ToolExecutionStartEvent
    | ToolExecutionEndEvent,
    Field(discriminator="type"),
]
