from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class StopReason(StrEnum):
    STOP = "stop"
    TOOL_USE = "tool_use"
    LENGTH = "length"  # output limit reached
    ERROR = "error"  # request or provider failure
    ABORTED = "aborted"  # request cancelled by user


class Usage(BaseModel):
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    reasoning: int | None = None
    # cost: Cost # TODO:

    @property
    def total_tokens(self) -> int:
        return self.input + self.output + self.cache_read + self.cache_write


class TextContent(BaseModel):
    type: Literal["text"] = "text"
    content: str


class ImageContent(BaseModel):
    type: Literal["image"] = "image"
    content: str
    mime_type: str


class ThinkingContent(BaseModel):
    """Model only thinking content. User can't use it"""

    type: Literal["thinking"] = "thinking"
    thinking: str
    thinking_signature: str | None = None
    redacted: bool = False


class ToolDescription(BaseModel):
    """Description about available tool that we send to agent in system prompt."""

    name: str
    description: str
    parameters: dict[str, Any]


class ToolCall(BaseModel):
    """Model requests ToolCall. We returns ToolResultMessage"""

    type: Literal["tool_call"] = "tool_call"
    id: str
    name: str
    arguments: dict[str, Any]


class ToolResultMessage(BaseModel):
    """Response to the ToolCall after execution."""

    role: Literal["tool_result"] = "tool_result"
    timestamp: datetime
    tool_call_id: str
    tool_name: str
    content: list[TextContent | ImageContent]
    is_error: bool


class UserMessage(BaseModel):
    role: Literal["user"] = "user"
    timestamp: datetime
    content: str | list[TextContent | ImageContent]


class AssistantMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    timestamp: datetime
    content: list[TextContent | ThinkingContent | ToolCall]
    usage: Usage
    stop_reason: StopReason
    error_message: str | None = None
    response_id: str | None = None


type Message = AssistantMessage | UserMessage | ToolResultMessage

# Events


class StartEvent(BaseModel):
    type: Literal["start"] = "start"
    partial: AssistantMessage


class TextDeltaEvent(BaseModel):
    type: Literal["text_delta"] = "text_delta"
    content_index: int
    delta: str
    partial: AssistantMessage


class DoneEvent(BaseModel):
    type: Literal["done"] = "done"
    reason: Literal[StopReason.STOP, StopReason.LENGTH, StopReason.TOOL_USE]
    message: AssistantMessage


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    reason: Literal[StopReason.ERROR, StopReason.ABORTED]
    error: AssistantMessage


type AssistantMessageEvent = Annotated[
    StartEvent | TextDeltaEvent | DoneEvent | ErrorEvent,
    Field(discriminator="type"),
]
