import json
import tempfile
import unittest
from pathlib import Path

from agent_core import AgentConfig, load_agent_config


class AgentConfigTest(unittest.TestCase):
    def test_loads_agent_behavior_config(self) -> None:
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

            self.assertEqual(
                load_agent_config(path),
                AgentConfig(
                    max_same_tool_calls=5,
                    max_output_tokens=100,
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
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                load_agent_config(path)


if __name__ == "__main__":
    unittest.main()
