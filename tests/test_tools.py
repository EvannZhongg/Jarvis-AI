import json
import os
import unittest
import tempfile
from pathlib import Path

from agent_core import (
    CommandExecutionResult,
    EditFileTool,
    ListDirectoryTool,
    ReadFileTool,
    SearchFilesTool,
    ShellApprovalPolicy,
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

    def test_returns_structured_policy_error_before_tool_execution(
        self,
    ) -> None:
        executed = []

        class RecordingTool(Tool):
            @property
            def definition(self) -> ToolDefinition:
                return ToolDefinition(
                    name="recording",
                    description="Record execution.",
                    parameters={"type": "object", "properties": {}},
                )

            def execute(self, arguments):
                executed.append(arguments)
                return None

        class DenyPolicy:
            def authorize(self, call):
                raise PermissionError(f"{call.name} was denied")

        registry = ToolRegistry((RecordingTool(),), policy=DenyPolicy())

        result = registry.execute(
            ToolCall(id="call-1", name="recording", arguments={})
        )

        self.assertEqual(executed, [])
        self.assertEqual(
            json.loads(result.to_content()),
            {
                "ok": False,
                "error": {
                    "type": "PermissionError",
                    "message": "recording was denied",
                },
            },
        )


class ReadFileToolTest(unittest.TestCase):
    def test_reads_utf8_file_with_line_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory))
            (workspace.path / "notes.txt").write_text(
                "你好，Jarvis。\n第二行\n",
                encoding="utf-8",
            )

            result = ReadFileTool(workspace).execute({"path": "notes.txt"})

            self.assertEqual(
                result,
                {
                    "path": "notes.txt",
                    "content": (
                        "1| 你好，Jarvis。\n"
                        "2| 第二行\n\n"
                        "(End of file — 2 lines total)"
                    ),
                },
            )

    def test_reads_requested_line_range(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory))
            (workspace.path / "notes.txt").write_text(
                "\n".join(f"line {number}" for number in range(1, 6)),
                encoding="utf-8",
            )

            result = ReadFileTool(workspace).execute(
                {
                    "path": "notes.txt",
                    "offset": 2,
                    "limit": 2,
                }
            )

            self.assertEqual(
                result,
                {
                    "path": "notes.txt",
                    "content": (
                        "2| line 2\n"
                        "3| line 3\n\n"
                        "(Showing lines 2-3 of 5. "
                        "Use offset=4 to continue.)"
                    ),
                },
            )

    def test_defaults_to_first_2000_lines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory))
            (workspace.path / "notes.txt").write_text(
                "\n".join(
                    f"line {number}" for number in range(1, 2002)
                ),
                encoding="utf-8",
            )

            result = ReadFileTool(workspace).execute({"path": "notes.txt"})

            content_lines = result["content"].splitlines()
            self.assertEqual(content_lines[0], "1| line 1")
            self.assertEqual(content_lines[1999], "2000| line 2000")
            self.assertEqual(
                content_lines[-1],
                (
                    "(Showing lines 1-2000 of 2001. "
                    "Use offset=2001 to continue.)"
                ),
            )

    def test_returns_end_marker_when_offset_reaches_end(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory))
            (workspace.path / "notes.txt").write_text(
                "first\nsecond\nthird\n",
                encoding="utf-8",
            )

            result = ReadFileTool(workspace).execute(
                {
                    "path": "notes.txt",
                    "offset": 3,
                    "limit": 10,
                }
            )

            self.assertEqual(
                result["content"],
                "3| third\n\n(End of file — 3 lines total)",
            )

    def test_returns_end_marker_for_offset_past_end(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory))
            (workspace.path / "notes.txt").write_text(
                "only line\n",
                encoding="utf-8",
            )

            result = ReadFileTool(workspace).execute(
                {"path": "notes.txt", "offset": 2}
            )

            self.assertEqual(
                result["content"],
                "(End of file — 1 lines total)",
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

    def test_validates_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tool = ReadFileTool(Workspace(Path(directory)))

            with self.assertRaisesRegex(ValueError, "non-empty string"):
                tool.execute({})
            with self.assertRaisesRegex(
                ValueError,
                "'offset' to be a positive integer",
            ):
                tool.execute({"path": "notes.txt", "offset": 0})
            with self.assertRaisesRegex(
                ValueError,
                "'offset' to be a positive integer",
            ):
                tool.execute({"path": "notes.txt", "offset": True})
            with self.assertRaisesRegex(
                ValueError,
                "'limit' to be a positive integer",
            ):
                tool.execute({"path": "notes.txt", "limit": 0})
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
    def test_delegates_command_to_executor(self) -> None:
        class RecordingExecutor:
            def __init__(self) -> None:
                self.commands = []

            def execute(self, command):
                self.commands.append(command)
                return CommandExecutionResult(
                    command=command,
                    exit_code=7,
                    stdout="output",
                    stderr="warning",
                )

        executor = RecordingExecutor()
        tool = ShellTool(executor)

        result = tool.execute({"command": "example command"})

        self.assertEqual(executor.commands, ["example command"])
        self.assertEqual(
            result,
            {
                "command": "example command",
                "exit_code": 7,
                "stdout": "output",
                "stderr": "warning",
            },
        )

    def test_requires_only_command_argument(self) -> None:
        class UnusedExecutor:
            def execute(self, command):
                raise AssertionError("executor should not be called")

        tool = ShellTool(UnusedExecutor())

        with self.assertRaisesRegex(ValueError, "non-empty string"):
            tool.execute({})
        with self.assertRaisesRegex(ValueError, "accepts only"):
            tool.execute({"command": "pwd", "extra": True})


class ShellApprovalPolicyTest(unittest.TestCase):
    def test_requests_approval_for_shell_command(self) -> None:
        requested_commands = []
        policy = ShellApprovalPolicy(
            lambda command: requested_commands.append(command) or True
        )

        policy.authorize(
            ToolCall(
                id="call-1",
                name="shell",
                arguments={"command": "pwd"},
            )
        )

        self.assertEqual(requested_commands, ["pwd"])

    def test_rejects_shell_command_without_approval(self) -> None:
        policy = ShellApprovalPolicy(lambda command: False)

        with self.assertRaisesRegex(PermissionError, "not approved"):
            policy.authorize(
                ToolCall(
                    id="call-1",
                    name="shell",
                    arguments={"command": "pwd"},
                )
            )

    def test_ignores_other_tools(self) -> None:
        requested_commands = []
        policy = ShellApprovalPolicy(
            lambda command: requested_commands.append(command) or False
        )

        policy.authorize(
            ToolCall(
                id="call-1",
                name="read_file",
                arguments={"path": "README.md"},
            )
        )

        self.assertEqual(requested_commands, [])


if __name__ == "__main__":
    unittest.main()
