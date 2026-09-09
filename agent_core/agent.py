from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable

from .llm import LLMProvider, LLMRequest
from .llm import LLMResponse
from .session import Message, Session
from .tools import Tool, ToolRegistry


@dataclass(frozen=True)
class AgentRunResult:
    request: LLMRequest
    response: LLMResponse
    items: tuple[Message, ...]
    user_input: str
    request_timestamp_utc: datetime
    response_timestamp_utc: datetime


class Agent:
    def __init__(
        self,
        provider: LLMProvider,
        session: Session,
        system_prompt: str,
        now: Callable[[], datetime] | None = None,
        tools: Iterable[Tool] = (),
    ) -> None:
        self._provider = provider
        self._session = session
        self._system_prompt = system_prompt
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._tools = ToolRegistry(tools)

    def run(self, user_input: str) -> AgentRunResult:
        turn_start = len(self._session.items)
        request_timestamp_utc = self._now().astimezone(timezone.utc)

        self._session.add_item(
            "user",
            user_input,
            timestamp_utc=request_timestamp_utc,
        )

        while True:
            request = LLMRequest(
                system_prompt=self._system_prompt,
                messages=tuple(
                    _format_timed_message(item)
                    for item in self._session.items
                ),
                tools=self._tools.definitions,
            )
            response = self._provider.complete(request)

            if response.tool_calls:
                self._session.add_item(
                    role="assistant",
                    content=response.content,
                    timestamp_utc=self._now().astimezone(timezone.utc),
                    tool_calls=response.tool_calls,
                )
                for tool_call in response.tool_calls:
                    tool_result = self._tools.execute(tool_call)
                    self._session.add_item(
                        role="tool",
                        content=tool_result.to_content(),
                        timestamp_utc=self._now().astimezone(timezone.utc),
                        tool_call_id=tool_call.id,
                    )
                continue

            if response.content is None:
                raise ValueError(
                    "LLM response must contain content or tool calls"
                )

            response_timestamp_utc = self._now().astimezone(timezone.utc)
            self._session.add_item(
                "assistant",
                response.content,
                timestamp_utc=response_timestamp_utc,
            )
            return AgentRunResult(
                request=request,
                response=response,
                items=tuple(self._session.items[turn_start:]),
                user_input=user_input,
                request_timestamp_utc=request_timestamp_utc,
                response_timestamp_utc=response_timestamp_utc,
            )


def _format_timed_message(message: Message) -> Message:
    content = message.content
    if (
        message.role != "tool"
        and message.timestamp_utc is not None
        and content is not None
    ):
        local_time = message.timestamp_utc.astimezone().isoformat(
            timespec="seconds"
        )
        content = f"[{local_time}] {content}"

    return Message(
        role=message.role,
        content=content,
        tool_calls=message.tool_calls,
        tool_call_id=message.tool_call_id,
    )
