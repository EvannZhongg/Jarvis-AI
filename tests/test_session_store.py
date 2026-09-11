import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from agent_core import (
    JsonlSessionStore,
    LLMRequest,
    LLMResponse,
    Message,
    TokenUsage,
    ToolCall,
)


class JsonlSessionStoreTest(unittest.TestCase):
    def test_lists_sessions_once_in_recent_turn_order_with_original_title(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonlSessionStore(Path(directory) / "sessions")
            self.assertEqual(store.list_sessions(), [])
            for index, (session_id, content) in enumerate((("first", "第一轮"), ("second", "另一个会话"), ("first", "后续问题"))):
                store.append_turn(session_id, LLMRequest("prompt", ()), LLMResponse("answer"), (
                    Message("user", content), Message("assistant", "answer"),
                ))
                os.utime(Path(directory) / "sessions" / f"{session_id}.jsonl", (index + 1, index + 1))
            self.assertEqual(store.list_sessions(), [
                {"session_id": "first", "title": "第一轮"},
                {"session_id": "second", "title": "另一个会话"},
            ])

    def test_appends_complete_turn_items(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sessions_directory = Path(directory) / "sessions"
            store = JsonlSessionStore(sessions_directory)
            request_time = datetime(2026, 9, 9, 8, 0, tzinfo=timezone.utc)
            response_time = datetime(2026, 9, 9, 8, 1, tzinfo=timezone.utc)
            request = LLMRequest(
                system_prompt="Be helpful.",
                messages=(Message(role="user", content="你好"),),
                max_output_tokens=100,
            )
            response = LLMResponse(
                content="你好！",
                usage=TokenUsage(
                    input_tokens=20,
                    output_tokens=8,
                    total_tokens=28,
                ),
            )
            items = (
                Message(
                    role="user",
                    content="你好",
                    timestamp_utc=request_time,
                ),
                Message(
                    role="assistant",
                    content="你好！",
                    timestamp_utc=response_time,
                ),
            )

            store.append_turn(
                "session-1",
                request,
                response,
                items,
            )

            path = sessions_directory / "session-1.jsonl"
            record = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(record["session_id"], "session-1")
            self.assertEqual(
                record["items"],
                [
                    {
                        "role": "user",
                        "content": "你好",
                        "timestamp_utc": "2026-09-09T08:00:00Z",
                    },
                    {
                        "role": "assistant",
                        "content": "你好！",
                        "timestamp_utc": "2026-09-09T08:01:00Z",
                    },
                ],
            )
            self.assertEqual(
                record["request"],
                {
                    "system_prompt": "Be helpful.",
                    "messages": [
                        {"role": "user", "content": "你好"},
                    ],
                    "max_output_tokens": 100,
                },
            )
            self.assertEqual(
                record["response"],
                {
                    "content": "你好！",
                    "usage": {
                        "input_tokens": 20,
                        "output_tokens": 8,
                        "total_tokens": 28,
                    },
                },
            )

    def test_loads_session_with_tool_call_items(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sessions_directory = Path(directory) / "sessions"
            store = JsonlSessionStore(sessions_directory)
            tool_call = ToolCall(
                id="call-1",
                name="read_file",
                arguments={"path": "README.md"},
            )
            first_items = (
                Message(
                    role="user",
                    content="read README.md",
                    timestamp_utc=datetime(
                        2026, 9, 9, 8, 0, tzinfo=timezone.utc
                    ),
                ),
                Message(
                    role="assistant",
                    content=None,
                    timestamp_utc=datetime(
                        2026, 9, 9, 8, 0, 1, tzinfo=timezone.utc
                    ),
                    tool_calls=(tool_call,),
                ),
                Message(
                    role="tool",
                    content='{"ok": true}',
                    timestamp_utc=datetime(
                        2026, 9, 9, 8, 0, 2, tzinfo=timezone.utc
                    ),
                    tool_call_id="call-1",
                ),
                Message(
                    role="assistant",
                    content="README.md was read.",
                    timestamp_utc=datetime(
                        2026, 9, 9, 8, 1, tzinfo=timezone.utc
                    ),
                ),
            )
            second_items = (
                Message(
                    role="user",
                    content="thanks",
                    timestamp_utc=datetime(
                        2026, 9, 9, 8, 2, tzinfo=timezone.utc
                    ),
                ),
                Message(
                    role="assistant",
                    content="You're welcome.",
                    timestamp_utc=datetime(
                        2026, 9, 9, 8, 3, tzinfo=timezone.utc
                    ),
                ),
            )

            store.append_turn(
                "session-1",
                LLMRequest(
                    system_prompt="Be helpful.",
                    messages=first_items[:-1],
                ),
                LLMResponse(content="README.md was read."),
                first_items,
            )
            store.append_turn(
                "session-2",
                LLMRequest(
                    system_prompt="Be helpful.",
                    messages=(Message(role="user", content="other"),),
                ),
                LLMResponse(content="other answer"),
                (
                    Message(role="user", content="other"),
                    Message(role="assistant", content="other answer"),
                ),
            )
            store.append_turn(
                "session-1",
                LLMRequest(
                    system_prompt="Be helpful.",
                    messages=(*first_items, second_items[0]),
                ),
                LLMResponse(content="You're welcome."),
                second_items,
            )

            session = store.load("session-1")

            self.assertEqual(
                session.items,
                [*first_items, *second_items],
            )
            self.assertEqual(
                sorted(path.name for path in sessions_directory.iterdir()),
                ["session-1.jsonl", "session-2.jsonl"],
            )

    def test_loads_missing_session_without_creating_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sessions_directory = Path(directory) / "sessions"
            store = JsonlSessionStore(sessions_directory)

            session = store.load("session-1")

            self.assertEqual(session.session_id, "session-1")
            self.assertEqual(session.items, [])
            self.assertFalse(sessions_directory.exists())

    def test_rejects_session_id_that_can_escape_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JsonlSessionStore(Path(directory) / "sessions")

            with self.assertRaises(ValueError):
                store.load("../session-1")


if __name__ == "__main__":
    unittest.main()
