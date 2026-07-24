from typing import Annotated, Literal

from pydantic import BaseModel, Field

from kiku_ai.messages import AssistantMessage, StopReason, ToolCall


class StartEvent(BaseModel):
    type: Literal["start"] = "start"
    partial: AssistantMessage


class TextStartEvent(BaseModel):
    type: Literal["text_start"] = "text_start"
    content_index: int
    partial: AssistantMessage


class TextDeltaEvent(BaseModel):
    type: Literal["text_delta"] = "text_delta"
    content_index: int
    delta: str
    partial: AssistantMessage


class TextEndEvent(BaseModel):
    type: Literal["text_end"] = "text_end"
    content_index: int
    content: str
    partial: AssistantMessage


class ThinkingStartEvent(BaseModel):
    type: Literal["thinking_start"] = "thinking_start"
    content_index: int
    partial: AssistantMessage


class ThinkingDeltaEvent(BaseModel):
    type: Literal["thinking_delta"] = "thinking_delta"
    content_index: int
    delta: str
    partial: AssistantMessage


class ThinkingEndEvent(BaseModel):
    type: Literal["thinking_end"] = "thinking_end"
    content_index: int
    content: str
    partial: AssistantMessage


class ToolCallStartEvent(BaseModel):
    type: Literal["tool_call_start"] = "tool_call_start"
    content_index: int
    partial: AssistantMessage


class ToolCallDeltaEvent(BaseModel):
    type: Literal["tool_call_delta"] = "tool_call_delta"
    content_index: int
    delta: str
    partial: AssistantMessage


class ToolCallEndEvent(BaseModel):
    type: Literal["tool_call_end"] = "tool_call_end"
    content_index: int
    tool_call: ToolCall
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
    StartEvent
    | TextStartEvent
    | TextDeltaEvent
    | TextEndEvent
    | ThinkingStartEvent
    | ThinkingDeltaEvent
    | ThinkingEndEvent
    | ToolCallStartEvent
    | ToolCallDeltaEvent
    | ToolCallEndEvent
    | DoneEvent
    | ErrorEvent,
    Field(discriminator="type"),
]
