from dataclasses import asdict

from ..execution import CommandExecutor
from .base import JSONValue, Tool, ToolDefinition


class ShellTool(Tool):
    def __init__(self, executor: CommandExecutor) -> None:
        self._executor = executor

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
                },
                "required": ["command"],
                "additionalProperties": False,
            },
        )

    def execute(self, arguments: dict[str, JSONValue]) -> JSONValue:
        command = arguments.get("command")
        if not isinstance(command, str) or not command:
            raise ValueError("shell requires a non-empty string 'command'")
        if set(arguments) != {"command"}:
            raise ValueError("shell accepts only the 'command' argument")
        return asdict(self._executor.execute(command))
