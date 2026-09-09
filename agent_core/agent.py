from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from .llm import LLMProvider, LLMRequest
from .llm import LLMResponse
from .session import Message, Session


@dataclass(frozen=True)
class AgentRunResult:
    request: LLMRequest
    response: LLMResponse
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
    ) -> None:
        self._provider = provider
        self._session = session
        self._system_prompt = system_prompt
        self._now = now or (lambda: datetime.now(timezone.utc))

    def run(self, user_input: str) -> AgentRunResult:
        request_timestamp_utc = self._now().astimezone(timezone.utc)

        self._session.add_message(
            "user",
            user_input,
            timestamp_utc=request_timestamp_utc,
        )

        request = LLMRequest(
            system_prompt=self._system_prompt,
            messages=tuple(
                Message(
                    role=message.role,
                    content=_format_timed_content(message),
                )
                for message in self._session.messages
            )
        )
        response = self._provider.complete(request)

        response_timestamp_utc = self._now().astimezone(timezone.utc)
        self._session.add_message(
            "assistant",
            response.content,
            timestamp_utc=response_timestamp_utc,
        )
        return AgentRunResult(
            request=request,
            response=response,
            user_input=user_input,
            request_timestamp_utc=request_timestamp_utc,
            response_timestamp_utc=response_timestamp_utc,
        )


def _format_timed_content(message: Message) -> str:
    if message.timestamp_utc is None:
        return message.content

    local_time = message.timestamp_utc.astimezone().isoformat(timespec="seconds")
    return f"[{local_time}] {message.content}"
