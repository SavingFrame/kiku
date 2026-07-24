from typing import Any

from pydantic import BaseModel

from kiku_ai.messages import Message


class Tool(BaseModel):
    """A tool declaration sent to a model."""

    name: str
    description: str
    parameters: dict[str, Any]


class Context(BaseModel):
    system_prompt: str | None = None
    messages: list[Message]
    tools: list[Tool] | None = None
