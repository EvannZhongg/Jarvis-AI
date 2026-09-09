import json
from datetime import datetime, timezone
from pathlib import Path

from .llm import LLMRequest, LLMResponse
from .session import Message, Session
from .tools import ToolCall


class JsonlSessionStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self, session_id: str) -> Session:
        if not self._path.exists():
            return Session(session_id=session_id)

        items = []
        with self._path.open(encoding="utf-8") as file:
            for line in file:
                record = json.loads(line)
                if record["session_id"] == session_id:
                    items.extend(
                        _message_from_dict(item)
                        for item in record["items"]
                    )

        return Session(session_id=session_id, items=items)

    def append_turn(
        self,
        session_id: str,
        request: LLMRequest,
        response: LLMResponse,
        items: tuple[Message, ...],
    ) -> None:
        record = {
            "session_id": session_id,
            "items": [_message_to_dict(item) for item in items],
            "request": {
                "system_prompt": request.system_prompt,
                "messages": [
                    _message_to_dict(message)
                    for message in request.messages
                ],
            },
            "response": {
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
        if response.tool_calls:
            record["response"]["tool_calls"] = [
                {
                    "id": tool_call.id,
                    "name": tool_call.name,
                    "arguments": tool_call.arguments,
                }
                for tool_call in response.tool_calls
            ]
        if request.tools:
            record["request"]["tools"] = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                }
                for tool in request.tools
            ]
        with self._path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def _message_to_dict(message: Message) -> dict[str, object]:
    data: dict[str, object] = {
        "role": message.role,
        "content": message.content,
    }
    if message.timestamp_utc is not None:
        data["timestamp_utc"] = _format_utc(message.timestamp_utc)
    if message.tool_calls:
        data["tool_calls"] = [
            {
                "id": tool_call.id,
                "name": tool_call.name,
                "arguments": tool_call.arguments,
            }
            for tool_call in message.tool_calls
        ]
    if message.tool_call_id is not None:
        data["tool_call_id"] = message.tool_call_id
    return data


def _message_from_dict(data: dict[str, object]) -> Message:
    timestamp_utc = data.get("timestamp_utc")
    tool_calls = data.get("tool_calls", [])
    return Message(
        role=data["role"],
        content=data.get("content"),
        timestamp_utc=(
            _parse_utc(timestamp_utc)
            if isinstance(timestamp_utc, str)
            else None
        ),
        tool_calls=tuple(
            ToolCall(
                id=tool_call["id"],
                name=tool_call["name"],
                arguments=tool_call["arguments"],
            )
            for tool_call in tool_calls
        ),
        tool_call_id=data.get("tool_call_id"),
    )


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )
