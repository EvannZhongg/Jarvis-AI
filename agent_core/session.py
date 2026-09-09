from dataclasses import dataclass, field
from typing import Literal
from uuid import uuid4


MessageRole = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class Message:
    role: MessageRole
    content: str


@dataclass
class Session:
    session_id: str = field(default_factory=lambda: str(uuid4()))
    messages: list[Message] = field(default_factory=list)

    def add_message(self, role: MessageRole, content: str) -> None:
        self.messages.append(Message(role=role, content=content))
