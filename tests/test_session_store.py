import json
import tempfile
import unittest
from datetime import timezone
from datetime import datetime
from pathlib import Path

from agent_core import (
    JsonlSessionStore,
    LLMRequest,
    LLMResponse,
    Message,
    TokenUsage,
)


class JsonlSessionStoreTest(unittest.TestCase):
    def test_appends_complete_turn_with_utc_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sessions.jsonl"
            store = JsonlSessionStore(path)
            request = LLMRequest(
                system_prompt="Be helpful.",
                messages=(
                    Message(role="user", content="你好"),
                )
            )
            response = LLMResponse(
                content="你好！",
                usage=TokenUsage(
                    input_tokens=20,
                    output_tokens=8,
                    total_tokens=28,
                ),
            )
            request_time = datetime(2026, 9, 9, 8, 0, tzinfo=timezone.utc)
            response_time = datetime(2026, 9, 9, 8, 1, tzinfo=timezone.utc)

            store.append_turn(
                "session-1",
                request,
                response,
                "你好",
                request_time,
                response_time,
            )

            record = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(record["session_id"], "session-1")
            self.assertEqual(
                record["request"]["timestamp_utc"],
                "2026-09-09T08:00:00Z",
            )
            self.assertEqual(record["request"]["input"], "你好")
            self.assertEqual(
                record["request"]["system_prompt"],
                "Be helpful.",
            )
            self.assertEqual(
                record["request"]["messages"],
                [
                    {"role": "user", "content": "你好"},
                ],
            )
            self.assertEqual(
                record["response"],
                {
                    "timestamp_utc": "2026-09-09T08:01:00Z",
                    "content": "你好！",
                    "usage": {
                        "input_tokens": 20,
                        "output_tokens": 8,
                        "total_tokens": 28,
                    },
                },
            )

    def test_loads_session_from_latest_complete_turn(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sessions.jsonl"
            store = JsonlSessionStore(path)
            store.append_turn(
                "session-1",
                LLMRequest(
                    system_prompt="Be helpful.",
                    messages=(
                        Message(role="user", content="first"),
                    )
                ),
                LLMResponse(content="first answer"),
                "first",
                datetime(2026, 9, 9, 8, 0, tzinfo=timezone.utc),
                datetime(2026, 9, 9, 8, 1, tzinfo=timezone.utc),
            )
            store.append_turn(
                "session-2",
                LLMRequest(
                    system_prompt="Be helpful.",
                    messages=(
                        Message(role="user", content="other"),
                    )
                ),
                LLMResponse(content="other answer"),
                "other",
                datetime(2026, 9, 9, 8, 1, tzinfo=timezone.utc),
                datetime(2026, 9, 9, 8, 2, tzinfo=timezone.utc),
            )
            store.append_turn(
                "session-1",
                LLMRequest(
                    system_prompt="Be helpful.",
                    messages=(
                        Message(role="user", content="first"),
                        Message(role="assistant", content="first answer"),
                        Message(role="user", content="second"),
                    )
                ),
                LLMResponse(content="second answer"),
                "second",
                datetime(2026, 9, 9, 8, 2, tzinfo=timezone.utc),
                datetime(2026, 9, 9, 8, 3, tzinfo=timezone.utc),
            )

            session = store.load("session-1")

            self.assertEqual(
                session.messages,
                [
                    Message(
                        role="user",
                        content="first",
                        timestamp_utc=datetime(
                            2026, 9, 9, 8, 0, tzinfo=timezone.utc
                        ),
                    ),
                    Message(
                        role="assistant",
                        content="first answer",
                        timestamp_utc=datetime(
                            2026, 9, 9, 8, 1, tzinfo=timezone.utc
                        ),
                    ),
                    Message(
                        role="user",
                        content="second",
                        timestamp_utc=datetime(
                            2026, 9, 9, 8, 2, tzinfo=timezone.utc
                        ),
                    ),
                    Message(
                        role="assistant",
                        content="second answer",
                        timestamp_utc=datetime(
                            2026, 9, 9, 8, 3, tzinfo=timezone.utc
                        ),
                    ),
                ],
            )


if __name__ == "__main__":
    unittest.main()
