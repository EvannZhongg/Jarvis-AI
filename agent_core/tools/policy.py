from typing import Callable

from .base import ToolCall


class ShellApprovalPolicy:
    def __init__(
        self,
        request_permission: Callable[[str], bool],
    ) -> None:
        self._request_permission = request_permission

    def authorize(self, call: ToolCall) -> None:
        if call.name != "shell":
            return

        command = call.arguments.get("command")
        if not isinstance(command, str) or not command:
            return
        if not self._request_permission(command):
            raise PermissionError("shell command was not approved")
