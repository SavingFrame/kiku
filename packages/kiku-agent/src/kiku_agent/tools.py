from abc import ABC, abstractmethod
from typing import Any

from jsonschema.protocols import Validator
from jsonschema.validators import validator_for
from kiku_ai import ImageContent, TextContent, Tool
from pydantic import BaseModel


class AgentToolResult(BaseModel):
    """The final result returned by an executable agent tool."""

    content: list[TextContent | ImageContent]
    details: Any = None


class AgentTool(Tool, ABC):
    """A model-visible tool declaration with an async executor."""

    @abstractmethod
    async def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any],
    ) -> AgentToolResult:
        """Execute a validated tool call."""
        raise NotImplementedError


def validate_tool_arguments(tool: AgentTool, arguments: dict[str, Any]) -> None:
    """Validate tool-call arguments against the tool's JSON Schema."""
    validator_class: type[Validator] = validator_for(tool.parameters)
    validator_class.check_schema(tool.parameters)
    validator_class(tool.parameters).validate(arguments)
