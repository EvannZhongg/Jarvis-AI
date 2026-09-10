import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AgentConfig:
    max_same_tool_calls: int
    max_output_tokens: int


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

    return AgentConfig(
        max_same_tool_calls=max_same_tool_calls,
        max_output_tokens=max_output_tokens,
    )


def _positive_integer(data: dict[str, object], field: str) -> int:
    value = data.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(
            f"config field '{field}' must be a positive integer"
        )
    return value
