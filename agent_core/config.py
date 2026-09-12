import json
from dataclasses import dataclass, field
from pathlib import Path

from .execution import (
    DEFAULT_COMMAND_TIMEOUT_SECONDS,
    MAX_COMMAND_TIMEOUT_SECONDS,
)
from .tools.config import ToolConfig, load_tool_config
from .mcp.config import McpConfig, load_mcp_config


DEFAULT_SHELL_TIMEOUT_SECONDS = DEFAULT_COMMAND_TIMEOUT_SECONDS
MAX_SHELL_TIMEOUT_SECONDS = MAX_COMMAND_TIMEOUT_SECONDS


@dataclass(frozen=True)
class ContextCompressionConfig:
    enabled: bool = True
    trigger_ratio: float | None = None
    target_ratio: float | None = None


@dataclass(frozen=True)
class AgentConfig:
    max_same_tool_calls: int
    max_output_tokens: int
    tools: ToolConfig
    shell_timeout_seconds: int = DEFAULT_SHELL_TIMEOUT_SECONDS
    context: ContextCompressionConfig = field(
        default_factory=ContextCompressionConfig
    )
    mcp: McpConfig = field(default_factory=McpConfig)


def load_agent_config(path: Path) -> AgentConfig:
    with path.open(encoding="utf-8") as file:
        data = json.load(file)

    max_same_tool_calls = _positive_integer(
        data,
        "max_same_tool_calls",
    )
    max_output_tokens = _positive_integer(
        data,
        "max_output_tokens",
    )
    shell_timeout_seconds = data.get(
        "shell_timeout_seconds",
        DEFAULT_SHELL_TIMEOUT_SECONDS,
    )
    if (
        isinstance(shell_timeout_seconds, bool)
        or not isinstance(shell_timeout_seconds, int)
        or shell_timeout_seconds < 1
        or shell_timeout_seconds > MAX_SHELL_TIMEOUT_SECONDS
    ):
        raise ValueError(
            "config field 'shell_timeout_seconds' must be an integer "
            f"between 1 and {MAX_SHELL_TIMEOUT_SECONDS}"
        )
    tools = load_tool_config(data.get("tools"))
    context = _context_config(data.get("context"))
    mcp = load_mcp_config(data.get("mcp"))

    return AgentConfig(
        max_same_tool_calls=max_same_tool_calls,
        max_output_tokens=max_output_tokens,
        tools=tools,
        shell_timeout_seconds=shell_timeout_seconds,
        context=context,
        mcp=mcp,
    )


def _context_config(value: object) -> ContextCompressionConfig:
    if value is None:
        return ContextCompressionConfig()
    if not isinstance(value, dict):
        raise ValueError("config field 'context' must be an object")
    compression = value.get("compression")
    if compression is None:
        return ContextCompressionConfig()
    if not isinstance(compression, dict):
        raise ValueError("config field 'context.compression' must be an object")
    enabled = compression.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("config field 'context.compression.enabled' must be a boolean")
    trigger = _optional_ratio(compression, "trigger_ratio")
    target = _optional_ratio(compression, "target_ratio")
    if trigger is not None and target is not None and target >= trigger:
        raise ValueError("context compression target_ratio must be less than trigger_ratio")
    return ContextCompressionConfig(enabled, trigger, target)


def _optional_ratio(data: dict[str, object], field: str) -> float | None:
    value = data.get(field)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value < 1:
        raise ValueError(f"config field 'context.compression.{field}' must be between 0 and 1")
    return float(value)


def _positive_integer(data: dict[str, object], field: str) -> int:
    value = data.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(
            f"config field '{field}' must be a positive integer"
        )
    return value
