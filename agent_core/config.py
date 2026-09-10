import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AgentConfig:
    max_same_tool_calls: int


def load_agent_config(path: Path) -> AgentConfig:
    with path.open(encoding="utf-8") as file:
        data = json.load(file)

    max_same_tool_calls = data.get("max_same_tool_calls")
    if (
        isinstance(max_same_tool_calls, bool)
        or not isinstance(max_same_tool_calls, int)
        or max_same_tool_calls < 1
    ):
        raise ValueError(
            "config field 'max_same_tool_calls' must be a positive integer"
        )

    return AgentConfig(max_same_tool_calls=max_same_tool_calls)
