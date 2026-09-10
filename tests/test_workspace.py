import tempfile
import unittest
from pathlib import Path

from agent_core import Workspace


class WorkspaceTest(unittest.TestCase):
    def test_resolves_existing_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory) / ".")

            self.assertEqual(workspace.path, Path(directory).resolve())

    def test_expands_user_directory(self) -> None:
        workspace = Workspace(Path("~"))

        self.assertEqual(workspace.path, Path.home().resolve())

    def test_rejects_missing_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing"

            with self.assertRaisesRegex(
                ValueError,
                "workspace must be an existing directory",
            ):
                Workspace(missing)


if __name__ == "__main__":
    unittest.main()
