import unittest
from datetime import datetime, timezone

from agent_core import Message, Session


class SessionTest(unittest.TestCase):
    def test_adds_items_in_order(self) -> None:
        session = Session(session_id="session-1")
        timestamp = datetime(2026, 9, 9, 8, 0, tzinfo=timezone.utc)

        session.add_item("user", "hello", timestamp)
        session.add_item("assistant", "hi")

        self.assertEqual(
            session.items,
            [
                Message(
                    role="user",
                    content="hello",
                    timestamp_utc=timestamp,
                ),
                Message(role="assistant", content="hi"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
