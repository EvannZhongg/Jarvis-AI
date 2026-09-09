import json
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
    def test_appends_complete_turn_items(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sessions.jsonl"
            store = JsonlSessionStore(path)
            request_time = datetime(2026, 9, 9, 8, 0, tzinfo=timezone.utc)
            response_time = datetime(2026, 9, 9, 8, 1, tzinfo=timezone.utc)
            request = LLMRequest(
                system_prompt="Be helpful.",
                messages=(Message(role="user", content="你好"),),
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
            path = Path(directory) / "sessions.jsonl"
            store = JsonlSessionStore(path)
            tool_call = ToolCall(
                id="call-1",
                name="get_current_time",
                arguments={},
            )
            first_items = (
                Message(
                    role="user",
                    content="what time is it?",
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
                    content="It is 16:00.",
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
                LLMResponse(content="It is 16:00."),
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


if __name__ == "__main__":
    unittest.main()
