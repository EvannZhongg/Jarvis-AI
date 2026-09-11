import tempfile
import time
import unittest
from pathlib import Path

from agent_core import SubprocessCommandExecutor
from agent_core.execution import MAX_COMMAND_OUTPUT_CHARS


class SubprocessCommandExecutorTest(unittest.TestCase):
    def test_executes_command_in_working_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            working_directory = Path(directory)
            executor = SubprocessCommandExecutor(working_directory)

            result = executor.execute(
                "printf 'hello'; "
                "printf 'warning' >&2; "
                "printf \"$PWD\" > command-output.txt"
            )

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.stdout, "hello")
            self.assertEqual(result.stderr, "warning")
            self.assertFalse(result.timed_out)
            self.assertEqual(result.timeout_seconds, 60)
            self.assertEqual(
                (working_directory / "command-output.txt").read_text(
                    encoding="utf-8"
                ),
                str(working_directory.resolve()),
            )

    def test_returns_nonzero_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executor = SubprocessCommandExecutor(Path(directory))

            result = executor.execute("printf 'failed' >&2; exit 7")

            self.assertEqual(result.exit_code, 7)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "failed")

    def test_times_out_and_terminates_the_process_group(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            working_directory = Path(directory)
            executor = SubprocessCommandExecutor(working_directory)

            result = executor.execute(
                "(sleep 2; printf 'alive' > child-output.txt) & wait",
                timeout_seconds=1,
            )
            time.sleep(1.5)

            self.assertTrue(result.timed_out)
            self.assertEqual(result.timeout_seconds, 1)
            self.assertLess(result.exit_code, 0)
            self.assertFalse(
                (working_directory / "child-output.txt").exists()
            )

    def test_limits_each_output_stream_and_keeps_both_ends(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executor = SubprocessCommandExecutor(Path(directory))

            result = executor.execute(
                "python -c \""
                "import sys; "
                "sys.stdout.write('START-OUT' + 'o' * 70000 + 'END-OUT'); "
                "sys.stderr.write('START-ERR' + 'e' * 70000 + 'END-ERR')"
                "\""
            )

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


if __name__ == "__main__":
    unittest.main()
