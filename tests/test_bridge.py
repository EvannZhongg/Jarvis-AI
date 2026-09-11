import io
import json
import unittest
from datetime import datetime, timezone

from agent_core import (
    AssistantMessageDeltaEvent,
    AssistantMessageEvent,
    ToolBatchStartedEvent,
    ToolCall,
    ToolCallEvent,
    ToolError,
    ToolResult,
    ToolResultEvent,
)
from agent_core.llm import TokenUsage
from interfaces.bridge.bridge import Bridge, Cancelled
from interfaces.bridge.protocol import (
    decode,
    event_to_message,
    format_timestamp,
    usage_to_dict,
)

TOOL_CALL = ToolCall(id="call-1", name="shell", arguments={"command": "ls"})
EVENT_TIME = datetime(2026, 9, 9, 8, 0, tzinfo=timezone.utc)


class ProtocolTest(unittest.TestCase):
    def test_encodes_assistant_delta(self) -> None:
        self.assertEqual(
            event_to_message(
                AssistantMessageDeltaEvent(text="hi", model_call_index=1),
                "t1",
            ),
            {
                "type": "assistant_delta",
                "turn_id": "t1",
                "text": "hi",
                "model_call_index": 1,
            },
        )

    def test_encodes_assistant_message_with_utc_timestamp(self) -> None:
        message = event_to_message(
            AssistantMessageEvent(
                content="done",
                timestamp_utc=EVENT_TIME,
                model_call_index=2,
            ),
            "t1",
        )
        self.assertEqual(message["type"], "assistant_message")
        self.assertEqual(message["content"], "done")
        self.assertTrue(str(message["timestamp_utc"]).endswith("Z"))

    def test_encodes_tool_call_events(self) -> None:
        self.assertEqual(
            event_to_message(
                ToolBatchStartedEvent(
                    model_call_index=1,
                    tool_calls=(TOOL_CALL,),
                ),
                "t1",
            )["tool_calls"],
            [{"id": "call-1", "name": "shell", "arguments": {"command": "ls"}}],
        )
        self.assertEqual(
            event_to_message(
                ToolCallEvent(
                    tool_call=TOOL_CALL,
                    tool_index=1,
                    tool_count=2,
                ),
                "t1",
            )["tool_count"],
            2,
        )

    def test_tool_result_reports_status_without_output(self) -> None:
        message = event_to_message(
            ToolResultEvent(
                tool_result=ToolResult(
                    tool_call_id="call-1",
                    name="shell",
                    output={"stdout": "x" * 5000},
                ),
                tool_index=1,
                tool_count=1,
            ),
            "t1",
        )
        self.assertTrue(message["ok"])
        self.assertIsNone(message["error"])
        # Output can be large and is offloaded to session artifacts.
        self.assertNotIn("output", message)

    def test_tool_result_reports_error(self) -> None:
        message = event_to_message(
            ToolResultEvent(
                tool_result=ToolResult(
                    tool_call_id="call-1",
                    name="shell",
                    error=ToolError(type="PermissionError", message="denied"),
                ),
                tool_index=1,
                tool_count=1,
            ),
            "t1",
        )
        self.assertFalse(message["ok"])
        self.assertEqual(
            message["error"],
            {"type": "PermissionError", "message": "denied"},
        )

    def test_usage_to_dict(self) -> None:
        self.assertIsNone(usage_to_dict(None))
        self.assertEqual(
            usage_to_dict(
                TokenUsage(input_tokens=1, output_tokens=2, total_tokens=3)
            ),
            {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
        )

    def test_format_timestamp_normalizes_to_utc(self) -> None:
        self.assertEqual(
            format_timestamp(EVENT_TIME),
            "2026-09-09T08:00:00.000000Z",
        )

    def test_decode_rejects_non_object_and_untyped_messages(self) -> None:
        with self.assertRaises(ValueError):
            decode("[1, 2]")
        with self.assertRaises(ValueError):
            decode('{"text": "hello"}')


def make_bridge(lines: list[str]) -> tuple[Bridge, io.StringIO]:
    stdin = io.StringIO("".join(f"{line}\n" for line in lines))
    stdout = io.StringIO()
    return Bridge(stdin, stdout), stdout


def emitted(stdout: io.StringIO) -> list[dict]:
    return [
        json.loads(line)
        for line in stdout.getvalue().splitlines()
        if line.strip()
    ]


class BridgeApprovalTest(unittest.TestCase):
    def test_approves_matching_request(self) -> None:
        bridge, stdout = make_bridge(
            ['{"type": "approval_response", "request_id": "None:1",'
             ' "approved": true}']
        )
        self.assertTrue(bridge.request_permission("ls"))
        self.assertEqual(emitted(stdout)[0]["command"], "ls")

    def test_denies_when_response_is_false(self) -> None:
        bridge, _ = make_bridge(
            ['{"type": "approval_response", "request_id": "None:1",'
             ' "approved": false}']
        )
        self.assertFalse(bridge.request_permission("rm -rf /"))

    def test_buffers_interleaved_messages_and_replays_them(self) -> None:
        """A typed-ahead turn must not be consumed as the answer."""
        bridge, _ = make_bridge(
            [
                '{"type": "user_turn", "turn_id": "t2", "text": "later"}',
                '{"type": "approval_response", "request_id": "None:1",'
                ' "approved": true}',
            ]
        )
        self.assertTrue(bridge.request_permission("ls"))

        deferred = bridge.read_message()
        assert deferred is not None
        self.assertEqual(deferred["type"], "user_turn")
        self.assertEqual(deferred["turn_id"], "t2")
        self.assertIsNone(bridge.read_message())

    def test_ignores_stale_request_id(self) -> None:
        bridge, _ = make_bridge(
            [
                '{"type": "approval_response", "request_id": "stale",'
                ' "approved": true}',
                '{"type": "approval_response", "request_id": "None:1",'
                ' "approved": false}',
            ]
        )
        self.assertFalse(bridge.request_permission("ls"))

    def test_cancels_when_input_ends(self) -> None:
        bridge, _ = make_bridge([])
        with self.assertRaises(Cancelled):
            bridge.request_permission("ls")

    def test_cancels_on_shutdown(self) -> None:
        bridge, _ = make_bridge(['{"type": "shutdown"}'])
        with self.assertRaises(Cancelled):
            bridge.request_permission("ls")


class BridgeServeTest(unittest.TestCase):
    def test_stops_on_shutdown(self) -> None:
        bridge, _ = make_bridge(['{"type": "shutdown"}'])
        bridge.serve()

    def test_stops_at_end_of_input(self) -> None:
        bridge, _ = make_bridge([])
        bridge.serve()

    def test_rejects_turn_before_start(self) -> None:
        bridge, _ = make_bridge(
            ['{"type": "user_turn", "turn_id": "t1", "text": "hi"}']
        )
        with self.assertRaises(RuntimeError):
            bridge.serve()

    def test_reports_malformed_input_as_fatal(self) -> None:
        bridge, stdout = make_bridge(["not json"])
        with self.assertRaises(SystemExit):
            bridge.serve()
        self.assertEqual(emitted(stdout)[0]["type"], "fatal")


if __name__ == "__main__":
    unittest.main()
