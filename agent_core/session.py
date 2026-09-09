from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import uuid4

from .tools import ToolCall


MessageRole = Literal["user", "assistant", "tool"]


@dataclass(frozen=True)
class Message:
    role: MessageRole
    content: str | None
    timestamp_utc: datetime | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None


@dataclass
class Session:
    session_id: str = field(default_factory=lambda: str(uuid4()))
    items: list[Message] = field(default_factory=list)

    def add_item(
        self,
        role: MessageRole,
        content: str | None,
        timestamp_utc: datetime | None = None,
        tool_calls: tuple[ToolCall, ...] = (),
        tool_call_id: str | None = None,
    ) -> None:
        self.items.append(
            Message(
                role=role,
                content=content,
                timestamp_utc=timestamp_utc,
                tool_calls=tool_calls,
                tool_call_id=tool_call_id,
            )
        )
