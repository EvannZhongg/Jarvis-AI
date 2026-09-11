import json
from pathlib import Path
from urllib.parse import quote

from .session_paths import session_directory
from .tools import ToolResult
from .workspace import Workspace


DEFAULT_MAX_TOOL_RESULT_CHARS = 16 * 1024
DEFAULT_TOOL_RESULT_PREVIEW_CHARS = 1200


class ToolResultNormalizer:
    def __init__(
        self,
        workspace: Workspace,
        session_id: str,
        max_chars: int = DEFAULT_MAX_TOOL_RESULT_CHARS,
        preview_chars: int = DEFAULT_TOOL_RESULT_PREVIEW_CHARS,
    ) -> None:
        if max_chars < 1:
            raise ValueError("max_chars must be a positive integer")
        if preview_chars < 1:
            raise ValueError("preview_chars must be a positive integer")

        self._workspace = workspace
        self._session_id = session_id
        self._max_chars = max_chars
        self._preview_chars = preview_chars
        session_directory(
            self._workspace.path / "sessions",
            self._session_id,
        )

    def normalize(self, result: ToolResult) -> str:
        content = result.to_content()
        size_chars = len(content)
        if size_chars <= self._max_chars:
            return content

        artifact_path = (
            Path("sessions")
            / self._session_id
            / f"{quote(result.tool_call_id, safe='')}.txt"
        )
        absolute_path = self._workspace.resolve_path(
            artifact_path.as_posix()
        )
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        absolute_path.write_text(content, encoding="utf-8")

        relative_path = artifact_path.as_posix()
        return json.dumps(
            {
                "artifact_path": relative_path,
                "size_chars": size_chars,
                "preview": content[: self._preview_chars],
                "read_instruction": (
                    "Use read_file with path "
                    f"'{relative_path}' to read the complete tool result."
                ),
            },
            ensure_ascii=False,
        )
