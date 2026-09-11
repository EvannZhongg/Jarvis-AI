import json
from dataclasses import dataclass
from pathlib import Path

from .execution import (
    DEFAULT_COMMAND_TIMEOUT_SECONDS,
    MAX_COMMAND_TIMEOUT_SECONDS,
)
from .tools.config import ToolConfig, load_tool_config


DEFAULT_SHELL_TIMEOUT_SECONDS = DEFAULT_COMMAND_TIMEOUT_SECONDS
MAX_SHELL_TIMEOUT_SECONDS = MAX_COMMAND_TIMEOUT_SECONDS


@dataclass(frozen=True)
class AgentConfig:
    max_same_tool_calls: int
    max_output_tokens: int
    tools: ToolConfig
    shell_timeout_seconds: int = DEFAULT_SHELL_TIMEOUT_SECONDS


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

    return AgentConfig(
        max_same_tool_calls=max_same_tool_calls,
        max_output_tokens=max_output_tokens,
        tools=tools,
        shell_timeout_seconds=shell_timeout_seconds,
    )


def _positive_integer(data: dict[str, object], field: str) -> int:
    value = data.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(
            f"config field '{field}' must be a positive integer"
        )
    return value
