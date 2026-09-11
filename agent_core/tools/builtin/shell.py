from dataclasses import asdict

from ...execution import (
    DEFAULT_COMMAND_TIMEOUT_SECONDS,
    MAX_COMMAND_TIMEOUT_SECONDS,
    CommandExecutor,
)
from ..base import JSONValue, Tool, ToolDefinition


class ShellTool(Tool):
    def __init__(
        self,
        executor: CommandExecutor,
        default_timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    ) -> None:
        if (
            isinstance(default_timeout_seconds, bool)
            or not isinstance(default_timeout_seconds, int)
            or default_timeout_seconds < 1
            or default_timeout_seconds > MAX_COMMAND_TIMEOUT_SECONDS
        ):
            raise ValueError(
                "default shell timeout must be an integer between 1 and "
                f"{MAX_COMMAND_TIMEOUT_SECONDS} seconds"
            )
        self._executor = executor
        self._default_timeout_seconds = default_timeout_seconds

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="shell",
            description="Execute a shell command in the workspace.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": (
                            "Shell command to execute with the workspace as "
                            "the current directory."
                        ),
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_COMMAND_TIMEOUT_SECONDS,
                        "description": (
                            "Optional timeout shorter than or equal to the "
                            "configured default timeout."
                        ),
                    },
                },
                "required": ["command"],
                "additionalProperties": False,
            },
        )

    def execute(self, arguments: dict[str, JSONValue]) -> JSONValue:
        command = arguments.get("command")
        timeout_seconds = arguments.get(
            "timeout_seconds",
            self._default_timeout_seconds,
        )
        if not isinstance(command, str) or not command:
            raise ValueError("shell requires a non-empty string 'command'")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int)
            or timeout_seconds < 1
            or timeout_seconds > MAX_COMMAND_TIMEOUT_SECONDS
        ):
            raise ValueError(
                "shell requires 'timeout_seconds' to be an integer "
                f"between 1 and {MAX_COMMAND_TIMEOUT_SECONDS}"
            )
        if timeout_seconds > self._default_timeout_seconds:
            raise ValueError(
                "shell 'timeout_seconds' cannot exceed the configured "
                f"default of {self._default_timeout_seconds} seconds"
            )
        if not set(arguments) <= {"command", "timeout_seconds"}:
            raise ValueError(
                "shell accepts only 'command' and 'timeout_seconds'"
            )
        return asdict(
            self._executor.execute(command, timeout_seconds)
        )
