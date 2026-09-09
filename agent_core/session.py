from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import uuid4


MessageRole = Literal["user", "assistant"]


@dataclass(frozen=True)
class Message:
    role: MessageRole
    content: str
    timestamp_utc: datetime | None = None


@dataclass
class Session:
    session_id: str = field(default_factory=lambda: str(uuid4()))
    messages: list[Message] = field(default_factory=list)

    def add_message(
        self,
        role: MessageRole,
        content: str,
        timestamp_utc: datetime | None = None,
    ) -> None:
        self.messages.append(
            Message(
                role=role,
                content=content,
                timestamp_utc=timestamp_utc,
            )
        )
