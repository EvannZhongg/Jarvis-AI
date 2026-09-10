from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Workspace:
    path: Path

    def __post_init__(self) -> None:
        resolved_path = self.path.expanduser().resolve()
        if not resolved_path.is_dir():
            raise ValueError(
                f"workspace must be an existing directory: {resolved_path}"
            )
        object.__setattr__(self, "path", resolved_path)
