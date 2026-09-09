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

        messages = []
        with self._path.open(encoding="utf-8") as file:
            for line in file:
                record = json.loads(line)
                if record["session_id"] == session_id:
                    messages.extend(
                        [
                            Message(
                                role="user",
                                content=record["request"]["input"],
                                timestamp_utc=_parse_utc(
                                    record["request"]["timestamp_utc"]
                                ),
                            ),
                            Message(
                                role="assistant",
                                content=record["response"]["content"],
                                timestamp_utc=_parse_utc(
                                    record["response"]["timestamp_utc"]
                                ),
                            ),
                        ]
                    )

        return Session(session_id=session_id, messages=messages)

    def append_turn(
        self,
        session_id: str,
        request: LLMRequest,
        response: LLMResponse,
        user_input: str,
        request_timestamp_utc: datetime,
        response_timestamp_utc: datetime,
    ) -> None:
        record = {
            "session_id": session_id,
            "request": {
                "timestamp_utc": _format_utc(request_timestamp_utc),
                "input": user_input,
                "system_prompt": request.system_prompt,
                "messages": [
                    {"role": message.role, "content": message.content}
                    for message in request.messages
                ]
            },
            "response": {
                "timestamp_utc": _format_utc(response_timestamp_utc),
                "content": response.content,
                "usage": (
                    {
                        "input_tokens": response.usage.input_tokens,
                        "output_tokens": response.usage.output_tokens,
                        "total_tokens": response.usage.total_tokens,
                    }
                    if response.usage is not None
                    else None
                ),
            },
        }
        with self._path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )
