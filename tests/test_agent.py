import json
import unittest
from datetime import datetime, timezone

from agent_core import (
    Agent,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    Message,
    Session,
    Tool,
    ToolCall,
    ToolDefinition,
)

REQUEST_TIME = datetime(2026, 9, 9, 8, 0, tzinfo=timezone.utc)
TOOL_CALL_TIME = datetime(2026, 9, 9, 8, 0, 10, tzinfo=timezone.utc)
TOOL_RESULT_TIME = datetime(2026, 9, 9, 8, 0, 11, tzinfo=timezone.utc)
RESPONSE_TIME = datetime(2026, 9, 9, 8, 1, tzinfo=timezone.utc)


class MockProvider(LLMProvider):
    def __init__(self, responses: list[str | LLMResponse]) -> None:
        self._responses = iter(responses)
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        response = next(self._responses)
        if isinstance(response, str):
            return LLMResponse(content=response)
        return response


class EchoTool(Tool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="echo",
            description="Echo the provided text.",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                },
                "required": ["text"],
                "additionalProperties": False,
            },
        )

    def execute(self, arguments):
        return {"text": arguments["text"]}


def clock(*values: datetime):
    times = iter(values)
    return lambda: next(times)


class AgentTest(unittest.TestCase):
    def test_calls_provider_and_writes_user_and_assistant_items(self) -> None:
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
            session.items,
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
            session.items,
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

    def test_executes_tool_calls_and_continues_until_final_response(self) -> None:
        tool_call = ToolCall(
            id="call-1",
            name="echo",
            arguments={"text": "hello"},
        )
        provider = MockProvider(
            [
                LLMResponse(content=None, tool_calls=(tool_call,)),
                LLMResponse(content="tool completed"),
            ]
        )
        session = Session(session_id="session-1")
        agent = Agent(
            provider=provider,
            session=session,
            system_prompt="You are helpful.",
            now=clock(
                REQUEST_TIME,
                TOOL_CALL_TIME,
                TOOL_RESULT_TIME,
                RESPONSE_TIME,
            ),
            tools=(EchoTool(),),
        )

        result = agent.run("use the echo tool")

        self.assertEqual(result.response.content, "tool completed")
        self.assertEqual(len(provider.requests), 2)
        self.assertEqual(result.request, provider.requests[1])
        self.assertEqual(
            provider.requests[0].tools,
            (EchoTool().definition,),
        )
        second_request_messages = provider.requests[1].messages
        self.assertEqual(
            [message.role for message in second_request_messages],
            ["user", "assistant", "tool"],
        )
        self.assertEqual(
            second_request_messages[1],
            Message(
                role="assistant",
                content=None,
                tool_calls=(tool_call,),
            ),
        )
        self.assertEqual(second_request_messages[2].tool_call_id, "call-1")
        self.assertEqual(
            json.loads(second_request_messages[2].content),
            {
                "ok": True,
                "output": {"text": "hello"},
            },
        )
        self.assertEqual(
            session.items,
            [
                Message(
                    role="user",
                    content="use the echo tool",
                    timestamp_utc=REQUEST_TIME,
                ),
                Message(
                    role="assistant",
                    content=None,
                    timestamp_utc=TOOL_CALL_TIME,
                    tool_calls=(tool_call,),
                ),
                Message(
                    role="tool",
                    content=second_request_messages[2].content,
                    timestamp_utc=TOOL_RESULT_TIME,
                    tool_call_id="call-1",
                ),
                Message(
                    role="assistant",
                    content="tool completed",
                    timestamp_utc=RESPONSE_TIME,
                ),
            ],
        )
        self.assertEqual(result.items, tuple(session.items))

    def test_returns_unknown_tool_error_to_model(self) -> None:
        provider = MockProvider(
            [
                LLMResponse(
                    content=None,
                    tool_calls=(
                        ToolCall(
                            id="call-1",
                            name="missing",
                            arguments={},
                        ),
                    ),
                ),
                LLMResponse(content="cannot use that tool"),
            ]
        )
        agent = Agent(
            provider=provider,
            session=Session(session_id="session-1"),
            system_prompt="You are helpful.",
            now=clock(
                REQUEST_TIME,
                TOOL_CALL_TIME,
                TOOL_RESULT_TIME,
                RESPONSE_TIME,
            ),
        )

        agent.run("use a missing tool")

        tool_message = provider.requests[1].messages[-1]
        self.assertEqual(tool_message.role, "tool")
        self.assertEqual(
            json.loads(tool_message.content),
            {
                "ok": False,
                "error": {
                    "type": "tool_not_found",
                    "message": "tool 'missing' is not registered",
                },
            },
        )


if __name__ == "__main__":
    unittest.main()
