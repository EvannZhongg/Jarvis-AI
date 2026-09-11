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

    def test_resolves_relative_path_within_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory))

            self.assertEqual(
                workspace.resolve_path("nested/file.txt"),
                workspace.path / "nested/file.txt",
            )

    def test_rejects_absolute_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory))
            outside = Path(directory).parent / "outside.txt"

            with self.assertRaisesRegex(ValueError, "must be relative"):
                workspace.resolve_path(str(outside))

    def test_rejects_path_outside_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory))

            with self.assertRaisesRegex(
                ValueError,
                "must stay within the workspace",
            ):
                workspace.resolve_path("../outside.txt")


if __name__ == "__main__":
    unittest.main()
