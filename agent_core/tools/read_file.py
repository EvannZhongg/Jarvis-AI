from .base import JSONValue, Tool, ToolDefinition
from ..workspace import Workspace


class ReadFileTool(Tool):
    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="read_file",
            description="Read the UTF-8 text content of a workspace file.",
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
            raise ValueError("read_file requires a non-empty string 'path'")
        if set(arguments) != {"path"}:
            raise ValueError("read_file accepts only the 'path' argument")

        file_path = self._workspace.resolve_path(path)
        content = file_path.read_bytes().decode("utf-8")
        return {
            "path": file_path.relative_to(self._workspace.path).as_posix(),
            "content": content,
        }
