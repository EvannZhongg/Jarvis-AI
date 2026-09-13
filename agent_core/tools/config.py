from dataclasses import dataclass


TOOL_NAMES = (
    "read_file",
    "edit_file",
    "search_files",
    "list_directory",
    "shell",
    "web_search",
    "subagent",
)


@dataclass(frozen=True)
class ToolConfig:
    enabled: frozenset[str]

    def is_enabled(self, name: str) -> bool:
        return name in self.enabled


def load_tool_config(data: object, *, allow_subagent: bool = True) -> ToolConfig:
    if not isinstance(data, dict):
        raise ValueError("config field 'tools' must be an object")

    allowed_names = set(TOOL_NAMES)
    if not allow_subagent:
        allowed_names.discard("subagent")
    unknown_names = set(data) - allowed_names
    if unknown_names:
        names = ", ".join(sorted(unknown_names))
        raise ValueError(f"unknown tool config field(s): {names}")

    enabled = []
    for name in TOOL_NAMES:
        if name not in allowed_names:
            continue
        value = data.get(name, False)
        if not isinstance(value, bool):
            raise ValueError(
                f"config field 'tools.{name}' must be a boolean"
            )
        if value:
            enabled.append(name)

    return ToolConfig(enabled=frozenset(enabled))
