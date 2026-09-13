from ..execution import DEFAULT_COMMAND_TIMEOUT_SECONDS, CommandExecutor
from ..workspace import Workspace
from .base import Tool
from .builtin import (
    EditFileTool,
    ListDirectoryTool,
    ReadFileTool,
    SearchFilesTool,
    ShellTool,
    SubagentRegistry,
    WebSearchTool,
)
from .config import ToolConfig


def create_builtin_tools(
    config: ToolConfig,
    workspace: Workspace,
    command_executor: CommandExecutor,
    shell_timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    subagent_registry: SubagentRegistry | None = None,
) -> tuple[Tool, ...]:
    tools: list[Tool] = []

    if config.is_enabled("read_file"):
        tools.append(ReadFileTool(workspace))
    if config.is_enabled("edit_file"):
        tools.append(EditFileTool(workspace))
    if config.is_enabled("search_files"):
        tools.append(SearchFilesTool(workspace))
    if config.is_enabled("list_directory"):
        tools.append(ListDirectoryTool(workspace))
    if config.is_enabled("shell"):
        tools.append(
            ShellTool(
                command_executor,
                default_timeout_seconds=shell_timeout_seconds,
            )
        )
    if config.is_enabled("web_search"):
        tools.append(WebSearchTool())
    if config.is_enabled("subagent") and subagent_registry is not None:
        tools.extend(subagent_registry.tools)

    return tuple(tools)


create_tools = create_builtin_tools
