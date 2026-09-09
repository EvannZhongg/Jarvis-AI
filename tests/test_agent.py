import unittest
from datetime import datetime, timezone

from agent_core import Agent, LLMProvider, LLMRequest, LLMResponse, Message, Session

REQUEST_TIME = datetime(2026, 9, 9, 8, 0, tzinfo=timezone.utc)
RESPONSE_TIME = datetime(2026, 9, 9, 8, 1, tzinfo=timezone.utc)


class MockProvider(LLMProvider):
    def __init__(self, responses: list[str]) -> None:
        self._responses = iter(responses)
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(content=next(self._responses))


def clock(*values: datetime):
    times = iter(values)
    return lambda: next(times)


class AgentTest(unittest.TestCase):
    def test_calls_provider_and_writes_user_and_assistant_messages(self) -> None:
        provider = MockProvider(["hello back"])
        session = Session(session_id="session-1")
        agent = Agent(
            provider=provider,
            session=session,
            system_prompt="You are helpful.",
            now=clock(REQUEST_TIME, RESPONSE_TIME),
        )

        result = agent.run("hello")

        self.assertEqual(result.response.content, "hello back")
        self.assertEqual(result.request_timestamp_utc, REQUEST_TIME)
        self.assertEqual(result.response_timestamp_utc, RESPONSE_TIME)
        self.assertEqual(result.request, provider.requests[0])
        request_messages = provider.requests[0].messages
        self.assertEqual(provider.requests[0].system_prompt, "You are helpful.")
        self.assertEqual(request_messages[0].role, "user")
        self.assertTrue(request_messages[0].content.startswith("["))
        self.assertTrue(request_messages[0].content.endswith("] hello"))
        self.assertEqual(
            session.messages,
            [
                Message(
                    role="user",
                    content="hello",
                    timestamp_utc=REQUEST_TIME,
                ),
                Message(
                    role="assistant",
                    content="hello back",
                    timestamp_utc=RESPONSE_TIME,
                ),
            ],
        )

    def test_mock_provider_receives_complete_multi_turn_context(self) -> None:
        provider = MockProvider(["first answer", "second answer"])
        session = Session(session_id="session-1")
        agent = Agent(
            provider=provider,
            session=session,
            system_prompt="You are helpful.",
            now=clock(
                datetime(2026, 9, 9, 8, 0, tzinfo=timezone.utc),
                datetime(2026, 9, 9, 8, 1, tzinfo=timezone.utc),
                datetime(2026, 9, 9, 9, 0, tzinfo=timezone.utc),
                datetime(2026, 9, 9, 9, 1, tzinfo=timezone.utc),
            ),
        )

        agent.run("first question")
        result = agent.run("second question")

        self.assertEqual(result.response.content, "second answer")
        self.assertEqual(result.request, provider.requests[1])
        self.assertEqual(provider.requests[1].system_prompt, "You are helpful.")
        history = provider.requests[1].messages
        self.assertEqual(
            [message.role for message in history],
            ["user", "assistant", "user"],
        )
        self.assertTrue(history[0].content.endswith("] first question"))
        self.assertTrue(history[1].content.endswith("] first answer"))
        self.assertTrue(history[2].content.endswith("] second question"))
        self.assertEqual(
            session.messages,
            [
                Message(
                    role="user",
                    content="first question",
                    timestamp_utc=datetime(
                        2026, 9, 9, 8, 0, tzinfo=timezone.utc
                    ),
                ),
                Message(
                    role="assistant",
                    content="first answer",
                    timestamp_utc=datetime(
                        2026, 9, 9, 8, 1, tzinfo=timezone.utc
                    ),
                ),
                Message(
                    role="user",
                    content="second question",
                    timestamp_utc=datetime(
                        2026, 9, 9, 9, 0, tzinfo=timezone.utc
                    ),
                ),
                Message(
                    role="assistant",
                    content="second answer",
                    timestamp_utc=datetime(
                        2026, 9, 9, 9, 1, tzinfo=timezone.utc
                    ),
                ),
            ],
        )


if __name__ == "__main__":
    unittest.main()
