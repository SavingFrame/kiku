from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class StopReason(StrEnum):
    STOP = "stop"
    TOOL_USE = "tool_use"
    LENGTH = "length"
    ERROR = "error"
    ABORTED = "aborted"


class Usage(BaseModel):
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    reasoning: int | None = None
    # cost: Cost  # TODO

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
    """Thinking content produced by a model."""

    type: Literal["thinking"] = "thinking"
    thinking: str
    thinking_signature: str | None = None
    redacted: bool = False


class ToolCall(BaseModel):
    """A request from the model to execute a tool."""

    type: Literal["tool_call"] = "tool_call"
    id: str
    name: str
    arguments: dict[str, Any]


class ToolResultMessage(BaseModel):
    """The result of executing a tool call."""

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


type Message = Annotated[
    AssistantMessage | UserMessage | ToolResultMessage,
    Field(discriminator="role"),
]
