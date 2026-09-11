from pathlib import Path


def session_directory(
    sessions_directory: Path,
    session_id: str,
) -> Path:
    _validate_session_id(session_id)
    return sessions_directory / session_id


def session_log_path(
    sessions_directory: Path,
    session_id: str,
) -> Path:
    return session_directory(sessions_directory, session_id) / (
        f"{session_id}.jsonl"
    )


def _validate_session_id(session_id: str) -> None:
    if (
        not session_id
        or session_id in {".", ".."}
        or "/" in session_id
        or "\\" in session_id
    ):
        raise ValueError(f"Invalid session id: {session_id!r}")
