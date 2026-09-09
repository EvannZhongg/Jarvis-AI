import json
import tempfile
import unittest
from datetime import timezone
from pathlib import Path

from agent_core import (
    JsonlSessionStore,
    LLMRequest,
    LLMResponse,
    Message,
)


class JsonlSessionStoreTest(unittest.TestCase):
    def test_appends_complete_turn_with_utc_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sessions.jsonl"
            store = JsonlSessionStore(path)
            request = LLMRequest(
                messages=(
                    Message(role="system", content="Be helpful."),
                    Message(role="user", content="你好"),
                )
            )
            response = LLMResponse(content="你好！")

            timestamp = store.append_turn("session-1", request, response)

            record = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(timestamp.tzinfo, timezone.utc)
            self.assertEqual(record["session_id"], "session-1")
            self.assertTrue(record["timestamp_utc"].endswith("Z"))
            self.assertEqual(
                record["request"]["messages"],
                [
                    {"role": "system", "content": "Be helpful."},
                    {"role": "user", "content": "你好"},
                ],
            )
            self.assertEqual(record["response"], {"content": "你好！"})

    def test_loads_session_from_latest_complete_turn(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sessions.jsonl"
            store = JsonlSessionStore(path)
            store.append_turn(
                "session-1",
                LLMRequest(
                    messages=(
                        Message(role="system", content="Be helpful."),
                        Message(role="user", content="first"),
                    )
                ),
                LLMResponse(content="first answer"),
            )
            store.append_turn(
                "session-2",
                LLMRequest(
                    messages=(
                        Message(role="system", content="Be helpful."),
                        Message(role="user", content="other"),
                    )
                ),
                LLMResponse(content="other answer"),
            )
            store.append_turn(
                "session-1",
                LLMRequest(
                    messages=(
                        Message(role="system", content="Be helpful."),
                        Message(role="user", content="first"),
                        Message(role="assistant", content="first answer"),
                        Message(role="user", content="second"),
                    )
                ),
                LLMResponse(content="second answer"),
            )

            session = store.load("session-1")

            self.assertEqual(
                session.messages,
                [
                    Message(role="user", content="first"),
                    Message(role="assistant", content="first answer"),
                    Message(role="user", content="second"),
                    Message(role="assistant", content="second answer"),
                ],
            )


if __name__ == "__main__":
    unittest.main()
