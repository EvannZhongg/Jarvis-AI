import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_cli.cli import (
    DEFAULT_AGENT_CONFIG_PATH,
    DEFAULT_CONFIG_PATH,
    main,
    parse_args,
)
from agent_cli.config import ModelConfig
from agent_core import (
    AgentConfig,
    EditFileTool,
    ListDirectoryTool,
    ReadFileTool,
    SearchFilesTool,
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
                    ),
                ),
                patch(
                    "agent_cli.cli.load_agent_config",
                    return_value=AgentConfig(max_same_tool_calls=5),
                ),
                patch("agent_cli.cli.JsonlSessionStore"),
                patch("agent_cli.cli.LiteLLMProvider"),
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
                    ),
                ),
                patch(
                    "agent_cli.cli.load_agent_config",
                    return_value=AgentConfig(max_same_tool_calls=5),
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


if __name__ == "__main__":
    unittest.main()
