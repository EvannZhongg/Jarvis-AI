import json
import unittest
from datetime import datetime, timedelta, timezone

from agent_core import (
    GetCurrentTimeTool,
    Tool,
    ToolCall,
    ToolDefinition,
    ToolRegistry,
)


class FailingTool(Tool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="failing",
            description="Always fails.",
            parameters={"type": "object", "properties": {}},
        )

    def execute(self, arguments):
        raise ValueError("bad input")


class ToolRegistryTest(unittest.TestCase):
    def test_returns_structured_execution_error(self) -> None:
        registry = ToolRegistry((FailingTool(),))

        result = registry.execute(
            ToolCall(id="call-1", name="failing", arguments={})
        )

        self.assertEqual(
            json.loads(result.to_content()),
            {
                "ok": False,
                "error": {
                    "type": "ValueError",
                    "message": "bad input",
                },
            },
        )

    def test_rejects_duplicate_tool_names(self) -> None:
        with self.assertRaisesRegex(ValueError, "already registered"):
            ToolRegistry((FailingTool(), FailingTool()))


class GetCurrentTimeToolTest(unittest.TestCase):
    def test_returns_iso_formatted_local_time(self) -> None:
        local_timezone = timezone(timedelta(hours=8))
        current_time = datetime(
            2026,
            9,
            10,
            0,
            30,
            tzinfo=local_timezone,
        )
        tool = GetCurrentTimeTool(now=lambda: current_time)

        self.assertEqual(
            tool.execute({}),
            {
                "datetime": current_time.astimezone().isoformat(
                    timespec="seconds"
                )
            },
        )


if __name__ == "__main__":
    unittest.main()
