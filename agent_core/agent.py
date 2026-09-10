from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable

from .config import AgentConfig
from .llm import LLMProvider, LLMRequest
from .llm import LLMResponse
from .session import Message, Session
from .tools import Tool, ToolRegistry


class ToolCallLimitExceededError(RuntimeError):
    def __init__(self, tool_name: str, limit: int) -> None:
        self.tool_name = tool_name
        self.limit = limit
        super().__init__(
            f"tool '{tool_name}' exceeded the maximum of "
            f"{limit} consecutive calls"
        )


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
        config: AgentConfig,
        now: Callable[[], datetime] | None = None,
        tools: Iterable[Tool] = (),
    ) -> None:
        self._provider = provider
        self._session = session
        self._system_prompt = system_prompt
        self._config = config
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._tools = ToolRegistry(tools)

    def run(self, user_input: str) -> AgentRunResult:
        turn_start = len(self._session.items)
        previous_tool_name: str | None = None
        consecutive_tool_calls = 0
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
                next_tool_name = previous_tool_name
                next_consecutive_calls = consecutive_tool_calls
                for tool_call in response.tool_calls:
                    if tool_call.name == next_tool_name:
                        next_consecutive_calls += 1
                    else:
                        next_tool_name = tool_call.name
                        next_consecutive_calls = 1

                    if (
                        next_consecutive_calls
                        > self._config.max_same_tool_calls
                    ):
                        raise ToolCallLimitExceededError(
                            tool_call.name,
                            self._config.max_same_tool_calls,
                        )
                previous_tool_name = next_tool_name
                consecutive_tool_calls = next_consecutive_calls

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
