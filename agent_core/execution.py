import os
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


DEFAULT_COMMAND_TIMEOUT_SECONDS = 60
MAX_COMMAND_TIMEOUT_SECONDS = 900
MAX_COMMAND_OUTPUT_CHARS = 50 * 1024


@dataclass(frozen=True)
class CommandExecutionResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    timeout_seconds: int | None = None


class CommandExecutor(Protocol):
    def execute(
        self,
        command: str,
        timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    ) -> CommandExecutionResult:
        raise NotImplementedError


class SubprocessCommandExecutor:
    def __init__(self, working_directory: Path) -> None:
        self._working_directory = working_directory

    def execute(
        self,
        command: str,
        timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    ) -> CommandExecutionResult:
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int)
            or timeout_seconds < 1
            or timeout_seconds > MAX_COMMAND_TIMEOUT_SECONDS
        ):
            raise ValueError(
                "command timeout must be an integer between 1 and "
                f"{MAX_COMMAND_TIMEOUT_SECONDS} seconds"
            )

        process = subprocess.Popen(
            command,
            shell=True,
            cwd=self._working_directory,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            start_new_session=True,
        )
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
        except BaseException:
            # The command runs in its own process group, so an interrupted
            # wait would otherwise leave it running detached.
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise

        stdout, stderr = _limit_output(stdout, stderr)
        return CommandExecutionResult(
            command=command,
            exit_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            timeout_seconds=timeout_seconds,
        )


def _limit_output(stdout: str, stderr: str) -> tuple[str, str]:
    return (
        _truncate_middle(stdout, MAX_COMMAND_OUTPUT_CHARS),
        _truncate_middle(stderr, MAX_COMMAND_OUTPUT_CHARS),
    )


def _truncate_middle(value: str, budget: int) -> str:
    if len(value) <= budget:
        return value

    omitted_chars = len(value) - budget
    while True:
        marker = (
            f"\n... [truncated {omitted_chars} characters] ...\n"
        )
        kept_chars = max(0, budget - len(marker))
        next_omitted_chars = len(value) - kept_chars
        if next_omitted_chars == omitted_chars:
            break
        omitted_chars = next_omitted_chars

    head_chars = (kept_chars + 1) // 2
    tail_chars = kept_chars // 2
    tail = value[-tail_chars:] if tail_chars else ""
    return value[:head_chars] + marker + tail
