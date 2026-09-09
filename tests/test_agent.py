import unittest

from agent_core import Agent, LLMProvider, LLMRequest, LLMResponse, Message, Session


class MockProvider(LLMProvider):
    def __init__(self, responses: list[str]) -> None:
        self._responses = iter(responses)
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(content=next(self._responses))


class AgentTest(unittest.TestCase):
    def test_calls_provider_and_writes_user_and_assistant_messages(self) -> None:
        provider = MockProvider(["hello back"])
        session = Session(session_id="session-1")
        agent = Agent(
            provider=provider,
            session=session,
            system_prompt="You are helpful.",
        )

        result = agent.run("hello")

        self.assertEqual(result.response.content, "hello back")
        self.assertEqual(result.request, provider.requests[0])
        self.assertEqual(
            provider.requests,
            [
                LLMRequest(
                    messages=(
                        Message(role="system", content="You are helpful."),
                        Message(role="user", content="hello"),
                    ),
                )
            ],
        )
        self.assertEqual(
            session.messages,
            [
                Message(role="user", content="hello"),
                Message(role="assistant", content="hello back"),
            ],
        )

    def test_mock_provider_receives_complete_multi_turn_context(self) -> None:
        provider = MockProvider(["first answer", "second answer"])
        session = Session(session_id="session-1")
        agent = Agent(
            provider=provider,
            session=session,
            system_prompt="You are helpful.",
        )

        agent.run("first question")
        result = agent.run("second question")

        self.assertEqual(result.response.content, "second answer")
        self.assertEqual(result.request, provider.requests[1])
        self.assertEqual(
            provider.requests[1].messages,
            (
                Message(role="system", content="You are helpful."),
                Message(role="user", content="first question"),
                Message(role="assistant", content="first answer"),
                Message(role="user", content="second question"),
            ),
        )
        self.assertEqual(
            session.messages,
            [
                Message(role="user", content="first question"),
                Message(role="assistant", content="first answer"),
                Message(role="user", content="second question"),
                Message(role="assistant", content="second answer"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
