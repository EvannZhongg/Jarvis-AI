import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

from agent_core import SubprocessCommandExecutor
from agent_core.execution import (
    MAX_COMMAND_OUTPUT_CHARS,
    _decode_output,
)


WINDOWS = os.name == "nt"


def _python_script_command(working_directory: Path, script: str) -> str:
    """Write a helper script into the workspace and run it by name.

    Running a script file keeps the command line free of the quoting that
    differs between cmd.exe and /bin/sh.
    """
    (working_directory / "command.py").write_text(script, encoding="utf-8")
    return f'"{sys.executable}" command.py'


class SubprocessCommandExecutorTest(unittest.TestCase):
    def test_executes_command_in_working_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            working_directory = Path(directory)
            executor = SubprocessCommandExecutor(working_directory)
            if WINDOWS:
                command = (
                    "echo hello & echo warning 1>&2 & "
                    "echo marker> command-output.txt"
                )
            else:
                command = (
                    "printf 'hello'; "
                    "printf 'warning' >&2; "
                    "printf 'marker' > command-output.txt"
                )

            result = executor.execute(command)

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.stdout.strip(), "hello")
            self.assertEqual(result.stderr.strip(), "warning")
            self.assertFalse(result.timed_out)
            self.assertEqual(result.timeout_seconds, 60)
            self.assertEqual(
                (working_directory / "command-output.txt")
                .read_text(encoding="utf-8")
                .strip(),
                "marker",
            )

    def test_returns_nonzero_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executor = SubprocessCommandExecutor(Path(directory))
            if WINDOWS:
                command = "echo failed 1>&2 & exit 7"
            else:
                command = "printf 'failed' >&2; exit 7"

            result = executor.execute(command)

            self.assertEqual(result.exit_code, 7)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr.strip(), "failed")

    def test_times_out_and_kills_the_command_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            working_directory = Path(directory)
            executor = SubprocessCommandExecutor(working_directory)
            command = _python_script_command(
                working_directory,
                "import time\n"
                "from pathlib import Path\n"
                "time.sleep(3)\n"
                "Path('child-output.txt').write_text('alive')\n",
            )

            result = executor.execute(command, timeout_seconds=1)
            time.sleep(3.5)

            self.assertTrue(result.timed_out)
            self.assertEqual(result.timeout_seconds, 1)
            self.assertFalse(
                (working_directory / "child-output.txt").exists()
            )

    def test_limits_each_output_stream_and_keeps_both_ends(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            working_directory = Path(directory)
            executor = SubprocessCommandExecutor(working_directory)
            command = _python_script_command(
                working_directory,
                "import sys\n"
                "sys.stdout.write('START-OUT' + 'o' * 70000 + 'END-OUT')\n"
                "sys.stderr.write('START-ERR' + 'e' * 70000 + 'END-ERR')\n",
            )

            result = executor.execute(command)

            self.assertLessEqual(len(result.stdout), MAX_COMMAND_OUTPUT_CHARS)
            self.assertLessEqual(len(result.stderr), MAX_COMMAND_OUTPUT_CHARS)
            self.assertTrue(result.stdout.startswith("START-OUT"))
            self.assertTrue(result.stdout.endswith("END-OUT"))
            self.assertTrue(result.stderr.startswith("START-ERR"))
            self.assertTrue(result.stderr.endswith("END-ERR"))
            self.assertRegex(
                result.stdout,
                r"\[truncated \d+ characters\]",
            )
            self.assertRegex(
                result.stderr,
                r"\[truncated \d+ characters\]",
            )

    def test_decodes_output_that_is_not_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            working_directory = Path(directory)
            executor = SubprocessCommandExecutor(working_directory)
            command = _python_script_command(
                working_directory,
                "import sys\n"
                "sys.stdout.buffer.write(b'\\xd6\\xd0\\xce\\xc4')\n"
                "sys.stderr.buffer.write(b'\\xd2\\xbb')\n",
            )

            result = executor.execute(command)

            self.assertEqual(result.exit_code, 0)
            self.assertNotEqual(result.stdout, "")
            self.assertNotEqual(result.stderr, "")

    def test_decodes_a_missing_stream_as_empty_text(self) -> None:
        self.assertEqual(_decode_output(None), "")
        self.assertEqual(_decode_output(b""), "")


if __name__ == "__main__":
    unittest.main()
