import tempfile
import unittest
from pathlib import Path

from agent_core import Workspace
from agent_core.prompts import load_subagent_prompt, load_system_prompt


class PromptsTest(unittest.TestCase):
    def test_loads_system_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory))
            prompt = load_system_prompt(workspace)

        self.assertTrue(prompt)
        self.assertIn("I am Nosis", prompt)
        self.assertIn(f"Current workspace: {workspace.path}", prompt)
        self.assertNotIn("{{workspace}}", prompt)
        self.assertNotIn(f"{{{{{workspace.path}}}}}", prompt)

    def test_loads_subagent_prompt_with_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory))
            prompt = load_subagent_prompt(workspace)

        self.assertTrue(prompt)
        self.assertIn(f"Current workspace: {workspace.path}", prompt)
        self.assertNotIn("{{workspace}}", prompt)
        self.assertNotIn(f"{{{{{workspace.path}}}}}", prompt)


if __name__ == "__main__":
    unittest.main()
