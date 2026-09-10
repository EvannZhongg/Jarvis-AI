import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class CommandExecutionResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str


class CommandExecutor(Protocol):
    def execute(self, command: str) -> CommandExecutionResult:
        raise NotImplementedError


class SubprocessCommandExecutor:
    def __init__(self, working_directory: Path) -> None:
        self._working_directory = working_directory

    def execute(self, command: str) -> CommandExecutionResult:
        completed = subprocess.run(
            command,
            shell=True,
            cwd=self._working_directory,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        return CommandExecutionResult(
            command=command,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
