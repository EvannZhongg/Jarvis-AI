import re
from typing import TYPE_CHECKING, Any

from ..tools import JSONValue, Tool, ToolDefinition

if TYPE_CHECKING:
    from .manager import McpClientManager


_INVALID_TOOL_NAME = re.compile(r"[^A-Za-z0-9_-]")


def qualified_tool_name(server_name: str, tool_name: str) -> str:
    normalized = _INVALID_TOOL_NAME.sub("_", tool_name)
    if not normalized:
        raise ValueError(
            f"MCP server '{server_name}' returned an empty tool name"
        )
    return f"mcp__{server_name}__{normalized}"


class McpTool(Tool):
    def __init__(
        self,
        manager: "McpClientManager",
        server_name: str,
        remote_name: str,
        description: str | None,
        input_schema: dict[str, Any],
    ) -> None:
        self._manager = manager
        self.server_name = server_name
        self.remote_name = remote_name
        self._definition = ToolDefinition(
            name=qualified_tool_name(server_name, remote_name),
            description=description or f"MCP tool {remote_name}",
            parameters=input_schema,
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def execute(self, arguments: dict[str, JSONValue]) -> JSONValue:
        return self._manager.call_tool(
            self.server_name,
            self.remote_name,
            arguments,
        )
