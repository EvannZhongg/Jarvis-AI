import re

from ..base import JSONValue, Tool, ToolDefinition
from ...workspace import Workspace


class SearchFilesTool(Tool):
    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="search_files",
            description=(
                "Search UTF-8 workspace files recursively with a regular "
                "expression."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Directory path relative to the workspace root."
                        ),
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Python regular expression to search.",
                    },
                },
                "required": ["path", "pattern"],
                "additionalProperties": False,
            },
        )

    def execute(self, arguments: dict[str, JSONValue]) -> JSONValue:
        path = arguments.get("path")
        pattern = arguments.get("pattern")
        if not isinstance(path, str) or not path:
            raise ValueError(
                "search_files requires a non-empty string 'path'"
            )
        if not isinstance(pattern, str) or not pattern:
            raise ValueError(
                "search_files requires a non-empty string 'pattern'"
            )
        if set(arguments) != {"path", "pattern"}:
            raise ValueError(
                "search_files accepts only 'path' and 'pattern'"
            )

        directory_path = self._workspace.resolve_path(path)
        if not directory_path.is_dir():
            raise ValueError("search_files path must be a directory")

        expression = re.compile(pattern)
        matches = []
        files = sorted(
            (
                candidate
                for candidate in directory_path.rglob("*")
                if candidate.is_file() and not candidate.is_symlink()
            ),
            key=lambda candidate: candidate.relative_to(
                self._workspace.path
            ).as_posix(),
        )
        for file_path in files:
            try:
                content = file_path.read_bytes().decode("utf-8")
            except UnicodeDecodeError:
                continue

            for line_number, line in enumerate(
                content.splitlines(),
                start=1,
            ):
                if expression.search(line):
                    matches.append(
                        {
                            "path": file_path.relative_to(
                                self._workspace.path
                            ).as_posix(),
                            "line_number": line_number,
                            "line": line,
                        }
                    )

        return {
            "path": directory_path.relative_to(
                self._workspace.path
            ).as_posix(),
            "pattern": pattern,
            "matches": matches,
        }
