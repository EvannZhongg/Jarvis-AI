import json
import os
import unittest
import tempfile
from pathlib import Path

from agent_core import (
    EditFileTool,
    ListDirectoryTool,
    ReadFileTool,
    SearchFilesTool,
    ShellTool,
    Tool,
    ToolCall,
    ToolDefinition,
    ToolRegistry,
    Workspace,
)


class FailingTool(Tool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="failing",
            description="Always fails.",
            parameters={"type": "object", "properties": {}},
        )

    def execute(self, arguments):
        raise ValueError("bad input")


class ToolRegistryTest(unittest.TestCase):
    def test_returns_structured_execution_error(self) -> None:
        registry = ToolRegistry((FailingTool(),))

        result = registry.execute(
            ToolCall(id="call-1", name="failing", arguments={})
        )

        self.assertEqual(
            json.loads(result.to_content()),
            {
                "ok": False,
                "error": {
                    "type": "ValueError",
                    "message": "bad input",
                },
            },
        )

    def test_rejects_duplicate_tool_names(self) -> None:
        with self.assertRaisesRegex(ValueError, "already registered"):
            ToolRegistry((FailingTool(), FailingTool()))


class ReadFileToolTest(unittest.TestCase):
    def test_reads_utf8_file_from_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory))
            (workspace.path / "notes.txt").write_text(
                "你好，Jarvis。\n",
                encoding="utf-8",
            )

            result = ReadFileTool(workspace).execute({"path": "notes.txt"})

            self.assertEqual(
                result,
                {
                    "path": "notes.txt",
                    "content": "你好，Jarvis。\n",
                },
            )

    def test_rejects_path_outside_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory))

            with self.assertRaisesRegex(
                ValueError,
                "must stay within the workspace",
            ):
                ReadFileTool(workspace).execute({"path": "../outside.txt"})

    def test_rejects_symlink_to_file_outside_workspace(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            tempfile.TemporaryDirectory() as outside_directory,
        ):
            workspace = Workspace(Path(directory))
            outside_file = Path(outside_directory) / "outside.txt"
            outside_file.write_text("secret", encoding="utf-8")
            os.symlink(outside_file, workspace.path / "link.txt")

            with self.assertRaisesRegex(
                ValueError,
                "must stay within the workspace",
            ):
                ReadFileTool(workspace).execute({"path": "link.txt"})

    def test_requires_only_path_argument(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tool = ReadFileTool(Workspace(Path(directory)))

            with self.assertRaisesRegex(ValueError, "non-empty string"):
                tool.execute({})
            with self.assertRaisesRegex(ValueError, "accepts only"):
                tool.execute({"path": "notes.txt", "extra": True})


class EditFileToolTest(unittest.TestCase):
    def test_replaces_one_exact_text_occurrence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory))
            file_path = workspace.path / "notes.txt"
            file_path.write_text("hello world\n", encoding="utf-8")

            result = EditFileTool(workspace).execute(
                {
                    "path": "notes.txt",
                    "old_text": "world",
                    "new_text": "Jarvis",
                }
            )

            self.assertEqual(
                result,
                {
                    "path": "notes.txt",
                    "replacements": 1,
                },
            )
            self.assertEqual(
                file_path.read_text(encoding="utf-8"),
                "hello Jarvis\n",
            )

    def test_rejects_missing_old_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory))
            file_path = workspace.path / "notes.txt"
            file_path.write_text("hello\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "was not found"):
                EditFileTool(workspace).execute(
                    {
                        "path": "notes.txt",
                        "old_text": "missing",
                        "new_text": "replacement",
                    }
                )

            self.assertEqual(file_path.read_text(encoding="utf-8"), "hello\n")

    def test_rejects_non_unique_old_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory))
            file_path = workspace.path / "notes.txt"
            file_path.write_text("same same", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "appears 2 times"):
                EditFileTool(workspace).execute(
                    {
                        "path": "notes.txt",
                        "old_text": "same",
                        "new_text": "changed",
                    }
                )

            self.assertEqual(
                file_path.read_text(encoding="utf-8"),
                "same same",
            )

    def test_allows_deleting_old_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory))
            file_path = workspace.path / "notes.txt"
            file_path.write_text("remove me", encoding="utf-8")

            EditFileTool(workspace).execute(
                {
                    "path": "notes.txt",
                    "old_text": "remove",
                    "new_text": "",
                }
            )

            self.assertEqual(file_path.read_text(encoding="utf-8"), " me")

    def test_requires_exact_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tool = EditFileTool(Workspace(Path(directory)))

            with self.assertRaisesRegex(ValueError, "non-empty string 'path'"):
                tool.execute({})
            with self.assertRaisesRegex(ValueError, "accepts only"):
                tool.execute(
                    {
                        "path": "notes.txt",
                        "old_text": "old",
                        "new_text": "new",
                        "extra": True,
                    }
                )


class ListDirectoryToolTest(unittest.TestCase):
    def test_lists_immediate_entries_in_name_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory))
            (workspace.path / "z.txt").write_text("z", encoding="utf-8")
            (workspace.path / "a").mkdir()
            os.symlink(
                workspace.path / "z.txt",
                workspace.path / "link.txt",
            )

            result = ListDirectoryTool(workspace).execute({"path": "."})

            self.assertEqual(
                result,
                {
                    "path": ".",
                    "entries": [
                        {"name": "a", "type": "directory"},
                        {"name": "link.txt", "type": "symlink"},
                        {"name": "z.txt", "type": "file"},
                    ],
                },
            )

    def test_rejects_file_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory))
            (workspace.path / "notes.txt").write_text(
                "notes",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "must be a directory"):
                ListDirectoryTool(workspace).execute({"path": "notes.txt"})

    def test_rejects_path_outside_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tool = ListDirectoryTool(Workspace(Path(directory)))

            with self.assertRaisesRegex(
                ValueError,
                "must stay within the workspace",
            ):
                tool.execute({"path": ".."})


class SearchFilesToolTest(unittest.TestCase):
    def test_searches_utf8_files_recursively(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory))
            nested = workspace.path / "nested"
            nested.mkdir()
            (workspace.path / "root.txt").write_text(
                "first Jarvis\nsecond\n",
                encoding="utf-8",
            )
            (nested / "child.txt").write_text(
                "Jarvis child\njarvis lowercase\n",
                encoding="utf-8",
            )

            result = SearchFilesTool(workspace).execute(
                {"path": ".", "pattern": r"Jarvis"}
            )

            self.assertEqual(
                result,
                {
                    "path": ".",
                    "pattern": "Jarvis",
                    "matches": [
                        {
                            "path": "nested/child.txt",
                            "line_number": 1,
                            "line": "Jarvis child",
                        },
                        {
                            "path": "root.txt",
                            "line_number": 1,
                            "line": "first Jarvis",
                        },
                    ],
                },
            )

    def test_supports_regular_expressions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory))
            (workspace.path / "notes.txt").write_text(
                "item-12\nitem-x\n",
                encoding="utf-8",
            )

            result = SearchFilesTool(workspace).execute(
                {"path": ".", "pattern": r"item-\d+"}
            )

            self.assertEqual(len(result["matches"]), 1)
            self.assertEqual(result["matches"][0]["line"], "item-12")

    def test_skips_non_utf8_files_and_symlinks(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            tempfile.TemporaryDirectory() as outside_directory,
        ):
            workspace = Workspace(Path(directory))
            (workspace.path / "binary.bin").write_bytes(b"\xffJarvis")
            outside_file = Path(outside_directory) / "outside.txt"
            outside_file.write_text("Jarvis", encoding="utf-8")
            os.symlink(outside_file, workspace.path / "link.txt")

            result = SearchFilesTool(workspace).execute(
                {"path": ".", "pattern": "Jarvis"}
            )

            self.assertEqual(result["matches"], [])

    def test_rejects_path_outside_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tool = SearchFilesTool(Workspace(Path(directory)))

            with self.assertRaisesRegex(
                ValueError,
                "must stay within the workspace",
            ):
                tool.execute({"path": "..", "pattern": "Jarvis"})

    def test_rejects_file_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory))
            (workspace.path / "notes.txt").write_text(
                "Jarvis",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "must be a directory"):
                SearchFilesTool(workspace).execute(
                    {"path": "notes.txt", "pattern": "Jarvis"}
                )

    def test_rejects_invalid_regular_expression(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tool = SearchFilesTool(Workspace(Path(directory)))

            with self.assertRaisesRegex(Exception, "unterminated"):
                tool.execute({"path": ".", "pattern": "["})


class ShellToolTest(unittest.TestCase):
    def test_executes_command_in_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory))
            requested_commands = []
            tool = ShellTool(
                workspace,
                lambda command: requested_commands.append(command) or True,
            )

            result = tool.execute(
                {
                    "command": (
                        "printf 'hello'; "
                        "printf 'warning' >&2; "
                        "printf \"$PWD\" > command-output.txt"
                    )
                }
            )

            self.assertEqual(requested_commands, [result["command"]])
            self.assertEqual(result["exit_code"], 0)
            self.assertEqual(result["stdout"], "hello")
            self.assertEqual(result["stderr"], "warning")
            self.assertEqual(
                (workspace.path / "command-output.txt").read_text(
                    encoding="utf-8"
                ),
                str(workspace.path),
            )

    def test_returns_nonzero_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tool = ShellTool(
                Workspace(Path(directory)),
                lambda command: True,
            )

            result = tool.execute(
                {"command": "printf 'failed' >&2; exit 7"}
            )

            self.assertEqual(result["exit_code"], 7)
            self.assertEqual(result["stdout"], "")
            self.assertEqual(result["stderr"], "failed")

    def test_rejects_command_without_permission(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory))
            tool = ShellTool(workspace, lambda command: False)

            with self.assertRaisesRegex(PermissionError, "not approved"):
                tool.execute({"command": "touch should-not-exist"})

            self.assertFalse(
                (workspace.path / "should-not-exist").exists()
            )

    def test_requires_only_command_argument(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tool = ShellTool(
                Workspace(Path(directory)),
                lambda command: True,
            )

            with self.assertRaisesRegex(ValueError, "non-empty string"):
                tool.execute({})
            with self.assertRaisesRegex(ValueError, "accepts only"):
                tool.execute({"command": "pwd", "extra": True})


if __name__ == "__main__":
    unittest.main()
