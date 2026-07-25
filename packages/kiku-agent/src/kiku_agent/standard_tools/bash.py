import asyncio
import os
import signal
from contextlib import suppress
from pathlib import Path
from typing import Any

from kiku_ai import TextContent
from pydantic import PrivateAttr

from kiku_agent.tools import AgentTool, AgentToolResult


class BashCommandError(RuntimeError):
    """Raised when a Bash command exits unsuccessfully."""

    def __init__(self, command: str, return_code: int, stdout: str, stderr: str) -> None:
        self.command = command
        self.return_code = return_code
        self.stdout = stdout
        self.stderr = stderr

        output = BashTool._format_output(stdout, stderr)
        super().__init__(f"Command exited with status {return_code}: {command}\n{output}")


class BashTimeoutError(TimeoutError):
    """Raised when a Bash command exceeds its timeout."""


class BashTool(AgentTool):
    """Temporary local Bash command executor."""

    name: str = "bash"
    description: str = "Run a command with Bash in the working directory"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Command to execute with bash -lc",
            },
            "timeout": {
                "type": "number",
                "exclusiveMinimum": 0,
                "description": "Timeout in seconds",
            },
        },
        "required": ["command"],
        "additionalProperties": False,
    }

    _cwd: Path = PrivateAttr()
    _default_timeout: float = PrivateAttr()

    def __init__(
        self,
        *,
        cwd: str | Path = ".",
        default_timeout: float = 30.0,
    ) -> None:
        if default_timeout <= 0:
            raise ValueError("default_timeout must be greater than zero")
        super().__init__(**{})
        self._cwd = Path(cwd).resolve()
        self._default_timeout = default_timeout

    async def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any],
    ) -> AgentToolResult:
        del tool_call_id
        command = str(arguments["command"])
        timeout = float(arguments.get("timeout", self._default_timeout))
        process = await asyncio.create_subprocess_exec(
            "bash",
            "-lc",
            command,
            cwd=self._cwd,
            start_new_session=True,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
        except TimeoutError as error:
            await self._kill_process_group(process)
            raise BashTimeoutError(f"Command timed out after {timeout:g} seconds: {command}") from error
        except asyncio.CancelledError:
            await self._kill_process_group(process)
            raise

        stdout = stdout_bytes.decode(errors="replace")
        stderr = stderr_bytes.decode(errors="replace")
        return_code = process.returncode
        if return_code is None:
            raise RuntimeError("Bash process ended without a return code")
        if return_code != 0:
            raise BashCommandError(command, return_code, stdout, stderr)

        return AgentToolResult(
            content=[TextContent(content=self._format_output(stdout, stderr))],
            details={
                "command": command,
                "cwd": str(self._cwd),
                "exit_code": return_code,
                "stdout": stdout,
                "stderr": stderr,
            },
        )

    @staticmethod
    async def _kill_process_group(process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        await process.wait()

    @staticmethod
    def _format_output(stdout: str, stderr: str) -> str:
        if not stdout and not stderr:
            return "(no output)"
        if not stdout:
            return stderr
        if not stderr:
            return stdout
        separator = "" if stdout.endswith("\n") else "\n"
        return f"{stdout}{separator}{stderr}"
