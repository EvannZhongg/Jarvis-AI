import unittest

from agent_core.prompts import load_system_prompt


class PromptsTest(unittest.TestCase):
    def test_loads_system_prompt(self) -> None:
        prompt = load_system_prompt()

        self.assertTrue(prompt)
        self.assertIn("I am Jarvis", prompt)


if __name__ == "__main__":
    unittest.main()
