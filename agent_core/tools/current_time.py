from datetime import datetime
from typing import Callable

from .base import JSONValue, Tool, ToolDefinition


class GetCurrentTimeTool(Tool):
    def __init__(self, now: Callable[[], datetime] | None = None) -> None:
        self._now = now or (lambda: datetime.now().astimezone())

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="get_current_time",
            description="Get the current local date, time, and UTC offset.",
            parameters={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        )

    def execute(self, arguments: dict[str, JSONValue]) -> JSONValue:
        if arguments:
            raise ValueError("get_current_time does not accept arguments")

        current_time = self._now().astimezone()
        return {
            "datetime": current_time.isoformat(timespec="seconds"),
        }
