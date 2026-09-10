from .base import JSONValue, Tool, ToolDefinition
from ..workspace import Workspace


class ListDirectoryTool(Tool):
    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="list_directory",
            description="List the immediate entries in a workspace directory.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path relative to the workspace root.",
                    },
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        )

    def execute(self, arguments: dict[str, JSONValue]) -> JSONValue:
        path = arguments.get("path")
        if not isinstance(path, str) or not path:
            raise ValueError(
                "list_directory requires a non-empty string 'path'"
            )
        if set(arguments) != {"path"}:
            raise ValueError(
                "list_directory accepts only the 'path' argument"
            )

        directory_path = self._workspace.resolve_path(path)
        if not directory_path.is_dir():
            raise ValueError("list_directory path must be a directory")

        entries = []
        entries_by_name = sorted(
            directory_path.iterdir(),
            key=lambda item: item.name,
        )
        for entry in entries_by_name:
            if entry.is_symlink():
                entry_type = "symlink"
            elif entry.is_dir():
                entry_type = "directory"
            elif entry.is_file():
                entry_type = "file"
            else:
                entry_type = "other"
            entries.append(
                {
                    "name": entry.name,
                    "type": entry_type,
                }
            )

        return {
            "path": directory_path.relative_to(
                self._workspace.path
            ).as_posix(),
            "entries": entries,
        }
