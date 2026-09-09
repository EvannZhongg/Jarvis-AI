import unittest

from agent_core import Message, Session


class SessionTest(unittest.TestCase):
    def test_adds_messages_in_order(self) -> None:
        session = Session(session_id="session-1")

        session.add_message("user", "hello")
        session.add_message("assistant", "hi")

        self.assertEqual(
            session.messages,
            [
                Message(role="user", content="hello"),
                Message(role="assistant", content="hi"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
