from typing import Callable

from .base import ToolCall, ToolPolicy


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


class CompositeToolPolicy:
    def __init__(self, *policies: ToolPolicy) -> None:
        self._policies = tuple(policies)

    def authorize(self, call: ToolCall) -> None:
        for policy in self._policies:
            policy.authorize(call)


class McpApprovalPolicy:
    def __init__(
        self,
        request_permission: Callable[[ToolCall], bool],
        prompt_servers: set[str] | frozenset[str],
    ) -> None:
        self._request_permission = request_permission
        self._prompt_servers = frozenset(prompt_servers)

    def authorize(self, call: ToolCall) -> None:
        if not call.name.startswith("mcp__"):
            return
        parts = call.name.split("__", 2)
        if len(parts) != 3 or parts[1] not in self._prompt_servers:
            return
        if not self._request_permission(call):
            raise PermissionError("MCP tool call was not approved")
