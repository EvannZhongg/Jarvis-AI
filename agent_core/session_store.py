import json
from datetime import datetime, timezone
from pathlib import Path

from .llm import LLMRequest, LLMResponse
from .session import Message, Session


class JsonlSessionStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self, session_id: str) -> Session:
        if not self._path.exists():
            return Session(session_id=session_id)

        latest_record = None
        with self._path.open(encoding="utf-8") as file:
            for line in file:
                record = json.loads(line)
                if record["session_id"] == session_id:
                    latest_record = record

        if latest_record is None:
            return Session(session_id=session_id)

        messages = [
            Message(role=message["role"], content=message["content"])
            for message in latest_record["request"]["messages"]
            if message["role"] != "system"
        ]
        messages.append(
            Message(
                role="assistant",
                content=latest_record["response"]["content"],
            )
        )
        return Session(session_id=session_id, messages=messages)

    def append_turn(
        self,
        session_id: str,
        request: LLMRequest,
        response: LLMResponse,
    ) -> datetime:
        timestamp_utc = datetime.now(timezone.utc)
        record = {
            "session_id": session_id,
            "timestamp_utc": timestamp_utc.isoformat().replace("+00:00", "Z"),
            "request": {
                "messages": [
                    {"role": message.role, "content": message.content}
                    for message in request.messages
                ]
            },
            "response": {"content": response.content},
        }
        with self._path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")

        return timestamp_utc
