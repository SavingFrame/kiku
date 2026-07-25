from pathlib import Path

import pytest
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from kiku_agent import (
    BashCommandError,
    BashTimeoutError,
    BashTool,
    ReadTool,
    validate_tool_arguments,
)
from kiku_ai import TextContent


async def test_read_tool_reads_a_line_range_relative_to_cwd(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("one\ntwo\nthree\nfour", encoding="utf-8")
    tool = ReadTool(cwd=tmp_path)
    arguments = {"path": "notes.txt", "offset": 2, "limit": 2}

    validate_tool_arguments(tool, arguments)
    result = await tool.execute("call-1", arguments)

    assert result.content == [TextContent(content="two\nthree\n")]
    assert result.details == {
        "path": str(tmp_path / "notes.txt"),
        "offset": 2,
        "lines": 2,
        "total_lines": 4,
    }


async def test_read_tool_reads_the_whole_file_by_default(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("one\ntwo", encoding="utf-8")

    result = await ReadTool(cwd=tmp_path).execute("call-1", {"path": "notes.txt"})

    assert result.content == [TextContent(content="one\ntwo")]


def test_read_tool_schema_rejects_invalid_ranges() -> None:
    tool = ReadTool()

    with pytest.raises(JsonSchemaValidationError):
        validate_tool_arguments(tool, {"path": "notes.txt", "offset": 0})
    with pytest.raises(JsonSchemaValidationError):
        validate_tool_arguments(tool, {"path": "notes.txt", "limit": 0})


async def test_bash_tool_runs_in_cwd_and_captures_output(tmp_path: Path) -> None:
    tool = BashTool(cwd=tmp_path)
    arguments = {
        "command": "printf '%s\\n' \"$PWD\"; printf 'warning\\n' >&2",
        "timeout": 1,
    }

    validate_tool_arguments(tool, arguments)
    result = await tool.execute("call-1", arguments)

    assert result.content == [TextContent(content=f"{tmp_path}\nwarning\n")]
    assert result.details == {
        "command": arguments["command"],
        "cwd": str(tmp_path),
        "exit_code": 0,
        "stdout": f"{tmp_path}\n",
        "stderr": "warning\n",
    }


async def test_bash_tool_raises_for_nonzero_exit(tmp_path: Path) -> None:
    tool = BashTool(cwd=tmp_path)

    with pytest.raises(BashCommandError) as caught:
        await tool.execute("call-1", {"command": "printf 'failed' >&2; exit 7"})

    assert caught.value.return_code == 7
    assert caught.value.stdout == ""
    assert caught.value.stderr == "failed"


async def test_bash_tool_enforces_timeout(tmp_path: Path) -> None:
    tool = BashTool(cwd=tmp_path, default_timeout=0.01)

    with pytest.raises(BashTimeoutError, match="timed out"):
        await tool.execute("call-1", {"command": "sleep 1"})


def test_runtime_configuration_is_not_serialized(tmp_path: Path) -> None:
    read_tool = ReadTool(cwd=tmp_path)
    bash_tool = BashTool(cwd=tmp_path, default_timeout=5)

    assert set(read_tool.model_dump()) == {"name", "description", "parameters"}
    assert set(bash_tool.model_dump()) == {"name", "description", "parameters"}


def test_bash_tool_rejects_invalid_default_timeout() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        BashTool(default_timeout=0)
