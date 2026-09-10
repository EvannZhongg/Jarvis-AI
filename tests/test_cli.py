import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from agent_cli.cli import (
    DEFAULT_AGENT_CONFIG_PATH,
    DEFAULT_CONFIG_PATH,
    main,
    parse_args,
    print_agent_event,
    request_shell_permission,
)
from agent_cli.config import ModelConfig
from agent_core import (
    AgentConfig,
    AssistantMessageEvent,
    EditFileTool,
    ListDirectoryTool,
    ReadFileTool,
    SearchFilesTool,
    ShellApprovalPolicy,
    ShellTool,
    SubprocessCommandExecutor,
    ToolBatchStartedEvent,
    ToolCall,
    ToolCallEvent,
    ToolError,
    ToolResult,
    ToolResultEvent,
    ToolConfig,
    Workspace,
)


class CliArgumentsTest(unittest.TestCase):
    def test_defaults_workspace_to_current_directory_at_runtime(self) -> None:
        args = parse_args([])

        self.assertIsNone(args.workspace)
        self.assertEqual(args.config, DEFAULT_CONFIG_PATH)
        self.assertEqual(args.agent_config, DEFAULT_AGENT_CONFIG_PATH)

    def test_accepts_explicit_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            args = parse_args(["--workspace", directory])

            self.assertEqual(args.workspace, Path(directory))

    def test_main_uses_current_directory_as_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch(
                    "agent_cli.cli.Path.cwd",
                    return_value=Path(directory),
                ),
                patch("agent_cli.cli.load_dotenv"),
                patch(
                    "agent_cli.cli.load_config",
                    return_value=ModelConfig(
                        model="test/model",
                        url=None,
                        key=None,
                        max_context_tokens=1000,
                    ),
                ),
                patch(
                    "agent_cli.cli.load_agent_config",
                    return_value=AgentConfig(
                        max_same_tool_calls=5,
                        max_output_tokens=100,
                        tools=ToolConfig(
                            enabled=frozenset(
                                {
                                    "read_file",
                                    "edit_file",
                                    "search_files",
                                    "list_directory",
                                    "shell",
                                }
                            )
                        ),
                    ),
                ),
                patch("agent_cli.cli.JsonlSessionStore"),
                patch(
                    "agent_cli.cli.LiteLLMProvider"
                ) as provider_class,
                patch("agent_cli.cli.Agent") as agent_class,
                patch("builtins.input", return_value="quit"),
                patch("builtins.print"),
            ):
                main([])

            self.assertEqual(
                agent_class.call_args.kwargs["workspace"],
                Workspace(Path(directory)),
            )
            tools = agent_class.call_args.kwargs["tools"]
            self.assertIsInstance(tools[0], ReadFileTool)
            self.assertIsInstance(tools[1], EditFileTool)
            self.assertIsInstance(tools[2], SearchFilesTool)
            self.assertIsInstance(tools[3], ListDirectoryTool)
            self.assertIsInstance(tools[4], ShellTool)
            self.assertIsInstance(
                tools[4]._executor,
                SubprocessCommandExecutor,
            )
            self.assertIsInstance(
                agent_class.call_args.kwargs["tool_policy"],
                ShellApprovalPolicy,
            )
            provider_class.assert_called_once_with(
                model="test/model",
                base_url=None,
                api_key=None,
                max_context_tokens=1000,
            )

    def test_main_uses_explicit_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch("agent_cli.cli.load_dotenv"),
                patch(
                    "agent_cli.cli.load_config",
                    return_value=ModelConfig(
                        model="test/model",
                        url=None,
                        key=None,
                        max_context_tokens=None,
                    ),
                ),
                patch(
                    "agent_cli.cli.load_agent_config",
                    return_value=AgentConfig(
                        max_same_tool_calls=5,
                        max_output_tokens=100,
                        tools=ToolConfig(
                            enabled=frozenset(
                                {
                                    "read_file",
                                    "edit_file",
                                    "search_files",
                                    "list_directory",
                                    "shell",
                                }
                            )
                        ),
                    ),
                ),
                patch("agent_cli.cli.JsonlSessionStore"),
                patch("agent_cli.cli.LiteLLMProvider"),
                patch("agent_cli.cli.Agent") as agent_class,
                patch("builtins.input", return_value="quit"),
                patch("builtins.print"),
            ):
                main(["--workspace", directory])

            self.assertEqual(
                agent_class.call_args.kwargs["workspace"],
                Workspace(Path(directory)),
            )


class CliEventRenderingTest(unittest.TestCase):
    def test_prints_intermediate_assistant_message(self) -> None:
        timestamp = datetime(2026, 9, 10, 9, 15, 49, tzinfo=timezone.utc)

        with patch("builtins.print") as print_mock:
            print_agent_event(
                AssistantMessageEvent(
                    content="I'll take a look at the workspace structure.",
                    timestamp_utc=timestamp,
                    model_call_index=1,
                )
            )

        self.assertEqual(
            [call.args[0] for call in print_mock.call_args_list],
            [
                (
                    "\nAssistant · model call #1 "
                    f"[{timestamp.astimezone().isoformat(timespec='seconds')}]"
                ),
                "I'll take a look at the workspace structure.",
            ],
        )

    def test_omits_timestamp_only_assistant_message(self) -> None:
        timestamp = datetime(2026, 9, 10, 9, 15, 49, tzinfo=timezone.utc)

        with patch("builtins.print") as print_mock:
            print_agent_event(
                AssistantMessageEvent(
                    content="[2026-09-10T17:28:40+08:00]",
                    timestamp_utc=timestamp,
                    model_call_index=2,
                )
            )

        print_mock.assert_not_called()

    def test_prints_tool_call_and_success(self) -> None:
        tool_call = ToolCall(
            id="call-1",
            name="read_file",
            arguments={"path": "README.md"},
        )
        with patch("builtins.print") as print_mock:
            print_agent_event(
                ToolBatchStartedEvent(
                    model_call_index=2,
                    tool_calls=(tool_call,),
                )
            )
            print_agent_event(
                ToolCallEvent(
                    tool_call=tool_call,
                    tool_index=1,
                    tool_count=1,
                )
            )
            print_agent_event(
                ToolResultEvent(
                    tool_result=ToolResult(
                        tool_call_id="call-1",
                        name="read_file",
                        output={"path": "README.md", "content": "..."},
                    ),
                    tool_index=1,
                    tool_count=1,
                )
            )

        self.assertEqual(
            [call.args[0] for call in print_mock.call_args_list],
            [
                "\nTools · model call #2 · 1 call(s)",
                '  [1/1] → read_file {"path": "README.md"}',
                "        ✓ completed",
            ],
        )

    def test_prints_tool_error(self) -> None:
        with patch("builtins.print") as print_mock:
            print_agent_event(
                ToolResultEvent(
                    tool_result=ToolResult(
                        tool_call_id="call-1",
                        name="read_file",
                        error=ToolError(
                            type="ValueError",
                            message="file not found",
                        ),
                    ),
                    tool_index=1,
                    tool_count=2,
                )
            )

        print_mock.assert_called_once_with(
            "        ✗ failed: ValueError: file not found"
        )


class ShellPermissionTest(unittest.TestCase):
    def test_approves_yes_response(self) -> None:
        with (
            patch("builtins.input", return_value="yes"),
            patch("builtins.print"),
        ):
            approved = request_shell_permission("pwd")

        self.assertTrue(approved)

    def test_denies_by_default(self) -> None:
        with (
            patch("builtins.input", return_value=""),
            patch("builtins.print"),
        ):
            approved = request_shell_permission("pwd")

        self.assertFalse(approved)


if __name__ == "__main__":
    unittest.main()
