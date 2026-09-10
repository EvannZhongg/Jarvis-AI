from ..base import JSONValue, Tool, ToolDefinition
from ...workspace import Workspace


DEFAULT_READ_LIMIT = 2000


class ReadFileTool(Tool):
    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="read_file",
            description=(
                "Read a range of lines from a UTF-8 workspace file with "
                "line numbers."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path relative to the workspace root.",
                    },
                    "offset": {
                        "type": "integer",
                        "minimum": 1,
                        "default": 1,
                        "description": "First line to read, starting from 1.",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "default": DEFAULT_READ_LIMIT,
                        "description": "Maximum number of lines to return.",
                    },
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        )

    def execute(self, arguments: dict[str, JSONValue]) -> JSONValue:
        path = arguments.get("path")
        offset = arguments.get("offset", 1)
        limit = arguments.get("limit", DEFAULT_READ_LIMIT)

        if not isinstance(path, str) or not path:
            raise ValueError("read_file requires a non-empty string 'path'")
        if (
            isinstance(offset, bool)
            or not isinstance(offset, int)
            or offset < 1
        ):
            raise ValueError(
                "read_file requires 'offset' to be a positive integer"
            )
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or limit < 1
        ):
            raise ValueError(
                "read_file requires 'limit' to be a positive integer"
            )
        if not set(arguments) <= {"path", "offset", "limit"}:
            raise ValueError(
                "read_file accepts only 'path', 'offset', and 'limit'"
            )

        file_path = self._workspace.resolve_path(path)
        lines = file_path.read_bytes().decode("utf-8").splitlines()
        total = len(lines)
        start = offset - 1
        end = min(start + limit, total)
        numbered_lines = [
            f"{line_number}| {line}"
            for line_number, line in enumerate(
                lines[start:end],
                start=offset,
            )
        ]

        if end < total:
            status = (
                f"(Showing lines {offset}-{end} of {total}. "
                f"Use offset={end + 1} to continue.)"
            )
        else:
            status = f"(End of file — {total} lines total)"

        content = "\n".join(numbered_lines)
        if content:
            content = f"{content}\n\n{status}"
        else:
            content = status

        return {
            "path": file_path.relative_to(self._workspace.path).as_posix(),
            "content": content,
        }
