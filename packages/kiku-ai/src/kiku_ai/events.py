from typing import Annotated, Literal

from pydantic import BaseModel, Field

from kiku_ai.messages import AssistantMessage, StopReason


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
