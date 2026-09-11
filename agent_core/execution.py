import locale
import os
import shutil
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
            _shell_argv(command),
            cwd=self._working_directory,
            # Commands must never read the stream the UI protocol uses.
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_process_tree(process)
            stdout, stderr = process.communicate()
        except BaseException:
            # The command runs in its own process group, so an interrupted
            # wait would otherwise leave it running detached.
            _kill_process_tree(process)
            process.wait()
            raise

        stdout, stderr = _limit_output(
            _decode_output(stdout),
            _decode_output(stderr),
        )
        return CommandExecutionResult(
            command=command,
            exit_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            timeout_seconds=timeout_seconds,
        )


def _shell_argv(command: str) -> list[str]:
    """Build the argv that runs *command* in a POSIX shell.

    macOS and Linux provide one at /bin/sh. Windows does not, so Git
    Bash is used there to keep command syntax identical everywhere.
    """
    if os.name == "nt":
        return [_git_bash(), "--noprofile", "--norc", "-c", command]

    return ["/bin/sh", "-c", command]


def _git_bash() -> str:
    """Locate the Git Bash shipped with Git for Windows.

    The bash.exe in System32 launches WSL, which runs in a different
    filesystem and cannot see the workspace.
    """
    candidates = [shutil.which("bash")]
    program_files = os.environ.get("ProgramFiles")
    local_app_data = os.environ.get("LOCALAPPDATA")
    if program_files:
        git_root = Path(program_files) / "Git"
        candidates += [
            str(git_root / "bin" / "bash.exe"),
            str(git_root / "usr" / "bin" / "bash.exe"),
        ]
    if local_app_data:
        candidates.append(
            str(Path(local_app_data, "Programs", "Git", "bin", "bash.exe"))
        )

    for candidate in candidates:
        if (
            candidate is not None
            and Path(candidate).is_file()
            and not _is_wsl_bash(candidate)
        ):
            return candidate

    raise RuntimeError(
        "shell requires Git Bash on Windows; install Git for Windows from "
        "https://git-scm.com/download/win"
    )


def _is_wsl_bash(path: str) -> bool:
    """Report whether *path* is the WSL launcher in System32."""
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    wsl_launcher = Path(system_root) / "System32" / "bash.exe"
    return os.path.normcase(str(Path(path).resolve())) == os.path.normcase(
        str(wsl_launcher.resolve())
    )


def _kill_process_tree(process: subprocess.Popen[bytes]) -> None:
    """Kill the command together with the processes it started.

    os.killpg is POSIX-only, and on Windows killing the shell alone
    leaves the children it spawned holding the output pipes open.
    """
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return

    os.killpg(process.pid, signal.SIGKILL)


def _decode_output(data: bytes | None) -> str:
    """Turn captured output bytes into text.

    Programs on Windows write in the console or ANSI code page rather
    than UTF-8, and a stream that fails to decode is reported to the
    caller as None by subprocess.
    """
    if not data:
        return ""

    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode(
            locale.getpreferredencoding(False),
            errors="replace",
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
