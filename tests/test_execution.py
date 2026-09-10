import tempfile
import unittest
from pathlib import Path

from agent_core import SubprocessCommandExecutor


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


if __name__ == "__main__":
    unittest.main()
