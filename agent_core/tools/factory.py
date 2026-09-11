from ..execution import DEFAULT_COMMAND_TIMEOUT_SECONDS, CommandExecutor
from ..workspace import Workspace
from .base import Tool
from .builtin import (
    EditFileTool,
    ListDirectoryTool,
    ReadFileTool,
    SearchFilesTool,
    ShellTool,
)
from .config import ToolConfig


def create_tools(
    config: ToolConfig,
    workspace: Workspace,
    command_executor: CommandExecutor,
    shell_timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
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

    return tuple(tools)
