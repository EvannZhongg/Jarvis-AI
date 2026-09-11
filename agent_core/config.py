import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from .tools.config import ToolConfig, load_tool_config


DEFAULT_CONFIG_FILENAMES = ("provider_config.json", "agent_config.json")


def default_config_directory() -> Path:
    return Path.home() / ".jarvis"


DEFAULT_CONFIG_DIRECTORY = default_config_directory()
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIRECTORY / "provider_config.json"
DEFAULT_AGENT_CONFIG_PATH = DEFAULT_CONFIG_DIRECTORY / "agent_config.json"


def initialize_default_configs(directory: Path) -> tuple[Path, ...]:
    created = []
    defaults = files("agent_core.defaults")
    for filename in DEFAULT_CONFIG_FILENAMES:
        path = directory / filename
        if path.exists():
            continue
        directory.mkdir(parents=True, exist_ok=True)
        path.write_text(
            defaults.joinpath(filename).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        created.append(path)
    return tuple(created)


@dataclass(frozen=True)
class AgentConfig:
    max_same_tool_calls: int
    max_output_tokens: int
    tools: ToolConfig


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
    tools = load_tool_config(data.get("tools"))

    return AgentConfig(
        max_same_tool_calls=max_same_tool_calls,
        max_output_tokens=max_output_tokens,
        tools=tools,
    )


def _positive_integer(data: dict[str, object], field: str) -> int:
    value = data.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(
            f"config field '{field}' must be a positive integer"
        )
    return value
