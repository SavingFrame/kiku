import asyncio
from pathlib import Path
from typing import Any

from kiku_ai import TextContent
from pydantic import PrivateAttr

from kiku_agent.tools import AgentTool, AgentToolResult


class ReadTool(AgentTool):
    """Temporary local text-file reader."""

    name: str = "read"
    description: str = "Read a UTF-8 text file, optionally selecting a range of lines"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute path or path relative to the working directory",
            },
            "offset": {
                "type": "integer",
                "minimum": 1,
                "description": "One-based first line to read",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "description": "Maximum number of lines to read",
            },
        },
        "required": ["path"],
        "additionalProperties": False,
    }

    _cwd: Path = PrivateAttr()

    def __init__(self, *, cwd: str | Path = ".") -> None:
        super().__init__(**{})
        self._cwd = Path(cwd).resolve()

    async def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any],
    ) -> AgentToolResult:
        del tool_call_id
        path = self._cwd / str(arguments["path"])
        offset = int(arguments.get("offset", 1))
        limit_value = arguments.get("limit")
        limit = int(limit_value) if limit_value is not None else None

        text = await asyncio.to_thread(path.read_text, encoding="utf-8")
        lines = text.splitlines(keepends=True)
        start = offset - 1
        selected = lines[start:] if limit is None else lines[start : start + limit]

        return AgentToolResult(
            content=[TextContent(content="".join(selected))],
            details={
                "path": str(path),
                "offset": offset,
                "lines": len(selected),
                "total_lines": len(lines),
            },
        )
