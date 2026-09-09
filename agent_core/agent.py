from dataclasses import dataclass

from .llm import LLMProvider, LLMRequest
from .llm import LLMResponse
from .session import Message, Session


@dataclass(frozen=True)
class AgentRunResult:
    request: LLMRequest
    response: LLMResponse


class Agent:
    def __init__(
        self,
        provider: LLMProvider,
        session: Session,
        system_prompt: str,
    ) -> None:
        self._provider = provider
        self._session = session
        self._system_prompt = system_prompt

    def run(self, user_input: str) -> AgentRunResult:
        self._session.add_message("user", user_input)

        request = LLMRequest(
            messages=(
                Message(role="system", content=self._system_prompt),
                *self._session.messages,
            )
        )
        response = self._provider.complete(request)

        self._session.add_message("assistant", response.content)
        return AgentRunResult(request=request, response=response)
