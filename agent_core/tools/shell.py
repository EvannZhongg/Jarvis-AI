import subprocess
from typing import Callable

from .base import JSONValue, Tool, ToolDefinition
from ..workspace import Workspace


class ShellTool(Tool):
    def __init__(
        self,
        workspace: Workspace,
        request_permission: Callable[[str], bool],
    ) -> None:
        self._workspace = workspace
        self._request_permission = request_permission

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="shell",
            description=(
                "Execute a shell command in the workspace after user "
                "approval."
            ),
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
        if not self._request_permission(command):
            raise PermissionError("shell command was not approved")

        completed = subprocess.run(
            command,
            shell=True,
            cwd=self._workspace.path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        return {
            "command": command,
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
