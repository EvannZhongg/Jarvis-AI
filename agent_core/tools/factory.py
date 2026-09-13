from ..execution import DEFAULT_COMMAND_TIMEOUT_SECONDS, CommandExecutor
from ..llm import LLMProvider
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
    AnalyzeImageTool,
)
from .config import ToolConfig


def create_builtin_tools(
    config: ToolConfig,
    workspace: Workspace,
    command_executor: CommandExecutor,
    shell_timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    subagent_registry: SubagentRegistry | None = None,
    vision_provider: LLMProvider | None = None,
    sessions_directory=None,
) -> tuple[Tool, ...]:
    tools: list[Tool] = []

    if config.is_enabled("read_file"):
        tools.append(ReadFileTool(workspace, sessions_directory=sessions_directory))
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
    if config.is_enabled("analyze_image") and vision_provider is not None:
        tools.append(AnalyzeImageTool(vision_provider, workspace))
    if config.is_enabled("subagent") and subagent_registry is not None:
        tools.extend(subagent_registry.tools)

    return tuple(tools)
