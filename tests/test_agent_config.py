import json
import tempfile
import unittest
from pathlib import Path

from agent_core import AgentConfig, ToolConfig, load_agent_config


ENABLED_TOOLS = {
    "read_file": True,
    "edit_file": True,
    "search_files": True,
    "list_directory": True,
    "shell": True,
}


class AgentConfigTest(unittest.TestCase):
    def test_loads_agent_behavior_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "agent_config.json"
            path.write_text(
                json.dumps(
                    {
                        "max_same_tool_calls": 5,
                        "max_output_tokens": 100,
                        "tools": {
                            **ENABLED_TOOLS,
                            "edit_file": False,
                            "shell": False,
                        },
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                load_agent_config(path),
                AgentConfig(
                    max_same_tool_calls=5,
                    max_output_tokens=100,
                    tools=ToolConfig(
                        enabled=frozenset(
                            {
                                "read_file",
                                "search_files",
                                "list_directory",
                            }
                        )
                    ),
                ),
            )

    def test_rejects_non_positive_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "agent_config.json"
            path.write_text(
                json.dumps(
                    {
                        "max_same_tool_calls": 0,
                        "max_output_tokens": 100,
                        "tools": ENABLED_TOOLS,
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                load_agent_config(path)

    def test_rejects_boolean_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "agent_config.json"
            path.write_text(
                json.dumps(
                    {
                        "max_same_tool_calls": True,
                        "max_output_tokens": 100,
                        "tools": ENABLED_TOOLS,
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                load_agent_config(path)

    def test_rejects_non_positive_output_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "agent_config.json"
            path.write_text(
                json.dumps(
                    {
                        "max_same_tool_calls": 5,
                        "max_output_tokens": 0,
                        "tools": ENABLED_TOOLS,
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                load_agent_config(path)

    def test_rejects_missing_tool_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "agent_config.json"
            path.write_text(
                json.dumps(
                    {
                        "max_same_tool_calls": 5,
                        "max_output_tokens": 100,
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "'tools'.*object"):
                load_agent_config(path)

    def test_rejects_non_boolean_tool_setting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "agent_config.json"
            path.write_text(
                json.dumps(
                    {
                        "max_same_tool_calls": 5,
                        "max_output_tokens": 100,
                        "tools": {
                            **ENABLED_TOOLS,
                            "shell": "true",
                        },
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValueError,
                "tools.shell.*boolean",
            ):
                load_agent_config(path)

    def test_rejects_unknown_tool_setting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "agent_config.json"
            path.write_text(
                json.dumps(
                    {
                        "max_same_tool_calls": 5,
                        "max_output_tokens": 100,
                        "tools": {
                            **ENABLED_TOOLS,
                            "unknown": True,
                        },
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "unknown"):
                load_agent_config(path)


if __name__ == "__main__":
    unittest.main()
