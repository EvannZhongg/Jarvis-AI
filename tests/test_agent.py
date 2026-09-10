import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from agent_core import (
    Agent,
    AgentConfig,
    AssistantMessageEvent,
    ContextWindowExceededError,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    Message,
    Session,
    Tool,
    ToolBatchStartedEvent,
    ToolCall,
    ToolCallEvent,
    ToolCallLimitExceededError,
    ToolConfig,
    ToolDefinition,
    ToolResultEvent,
    Workspace,
)

REQUEST_TIME = datetime(2026, 9, 9, 8, 0, tzinfo=timezone.utc)
TOOL_CALL_TIME = datetime(2026, 9, 9, 8, 0, 10, tzinfo=timezone.utc)
TOOL_RESULT_TIME = datetime(2026, 9, 9, 8, 0, 11, tzinfo=timezone.utc)
RESPONSE_TIME = datetime(2026, 9, 9, 8, 1, tzinfo=timezone.utc)
AGENT_CONFIG = AgentConfig(
    max_same_tool_calls=5,
    max_output_tokens=100,
    tools=ToolConfig(enabled=frozenset()),
)
TEST_WORKSPACE = Workspace(Path(__file__).parent)


class MockProvider(LLMProvider):
    def __init__(
        self,
        responses: list[str | LLMResponse],
        input_tokens: int = 1,
        max_context_tokens: int = 1000,
    ) -> None:
        self._responses = iter(responses)
        self._input_tokens = input_tokens
        self._max_context_tokens = max_context_tokens
        self.counted_requests: list[LLMRequest] = []
        self.requests: list[LLMRequest] = []

    @property
    def max_context_tokens(self) -> int:
        return self._max_context_tokens

    def count_input_tokens(self, request: LLMRequest) -> int:
        self.counted_requests.append(request)
        return self._input_tokens

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
            config=AGENT_CONFIG,
            workspace=TEST_WORKSPACE,
            now=clock(REQUEST_TIME, RESPONSE_TIME),
        )

        result = agent.run("hello")

        self.assertEqual(result.response.content, "hello back")
        self.assertEqual(result.request_timestamp_utc, REQUEST_TIME)
        self.assertEqual(result.response_timestamp_utc, RESPONSE_TIME)
        self.assertEqual(result.request, provider.requests[0])
        request_messages = provider.requests[0].messages
        self.assertEqual(
            provider.requests[0].system_prompt,
            "You are helpful.",
        )
        self.assertEqual(provider.requests[0].max_output_tokens, 100)
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

    def test_rejects_context_before_calling_provider(self) -> None:
        provider = MockProvider(["unused"], input_tokens=901)
        session = Session(session_id="session-1")
        agent = Agent(
            provider=provider,
            session=session,
            system_prompt="You are helpful.",
            config=AGENT_CONFIG,
            workspace=TEST_WORKSPACE,
            now=clock(REQUEST_TIME),
        )

        with self.assertRaises(ContextWindowExceededError) as context:
            agent.run("hello")

        self.assertEqual(context.exception.input_tokens, 901)
        self.assertEqual(context.exception.max_context_tokens, 1000)
        self.assertEqual(context.exception.max_output_tokens, 100)
        self.assertEqual(context.exception.max_input_tokens, 900)
        self.assertEqual(len(provider.counted_requests), 1)
        self.assertEqual(provider.requests, [])

    def test_rejects_output_limit_not_smaller_than_context_limit(self) -> None:
        provider = MockProvider(["unused"], max_context_tokens=100)

        with self.assertRaises(ValueError):
            Agent(
                provider=provider,
                session=Session(session_id="session-1"),
                system_prompt="You are helpful.",
                config=AGENT_CONFIG,
                workspace=TEST_WORKSPACE,
            )

    def test_mock_provider_receives_complete_multi_turn_context(self) -> None:
        provider = MockProvider(["first answer", "second answer"])
        session = Session(session_id="session-1")
        agent = Agent(
            provider=provider,
            session=session,
            system_prompt="You are helpful.",
            config=AGENT_CONFIG,
            workspace=TEST_WORKSPACE,
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
        self.assertEqual(
            provider.requests[1].system_prompt,
            "You are helpful.",
        )
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
                LLMResponse(
                    content="I'll use the echo tool.",
                    tool_calls=(tool_call,),
                ),
                LLMResponse(content="tool completed"),
            ]
        )
        session = Session(session_id="session-1")
        agent = Agent(
            provider=provider,
            session=session,
            system_prompt="You are helpful.",
            config=AGENT_CONFIG,
            workspace=TEST_WORKSPACE,
            now=clock(
                REQUEST_TIME,
                TOOL_CALL_TIME,
                TOOL_RESULT_TIME,
                RESPONSE_TIME,
            ),
            tools=(EchoTool(),),
        )
        events = []

        result = agent.run("use the echo tool", on_event=events.append)

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
                content=(
                    "[2026-09-09T16:00:10+08:00] "
                    "I'll use the echo tool."
                ),
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
                    content="I'll use the echo tool.",
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
        self.assertEqual(
            events[0],
            AssistantMessageEvent(
                content="I'll use the echo tool.",
                timestamp_utc=TOOL_CALL_TIME,
                model_call_index=1,
            ),
        )
        self.assertEqual(
            events[1],
            ToolBatchStartedEvent(
                model_call_index=1,
                tool_calls=(tool_call,),
            ),
        )
        self.assertEqual(
            events[2],
            ToolCallEvent(
                tool_call=tool_call,
                tool_index=1,
                tool_count=1,
            ),
        )
        self.assertIsInstance(events[3], ToolResultEvent)
        self.assertEqual(events[3].tool_result.name, "echo")
        self.assertEqual(
            events[3].tool_result.output,
            {"text": "hello"},
        )
        self.assertEqual(
            events[4],
            AssistantMessageEvent(
                content="tool completed",
                timestamp_utc=RESPONSE_TIME,
                model_call_index=2,
            ),
        )

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
            config=AGENT_CONFIG,
            workspace=TEST_WORKSPACE,
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

    def test_stops_on_sixth_identical_tool_call(self) -> None:
        responses = [
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id=f"call-{index}",
                        name="echo",
                        arguments={"text": "hello"},
                    ),
                ),
            )
            for index in range(1, 7)
        ]
        provider = MockProvider(responses)
        session = Session(session_id="session-1")
        timestamps = [
            datetime(2026, 9, 9, 8, 0, index, tzinfo=timezone.utc)
            for index in range(11)
        ]
        agent = Agent(
            provider=provider,
            session=session,
            system_prompt="You are helpful.",
            config=AGENT_CONFIG,
            workspace=TEST_WORKSPACE,
            now=clock(*timestamps),
            tools=(EchoTool(),),
        )

        with self.assertRaises(ToolCallLimitExceededError) as context:
            agent.run("repeat the echo tool")

        self.assertEqual(context.exception.tool_name, "echo")
        self.assertEqual(context.exception.limit, 5)
        self.assertEqual(len(provider.requests), 6)
        self.assertEqual(
            [item.role for item in session.items],
            ["user", *(["assistant", "tool"] * 5)],
        )

    def test_same_tool_with_different_arguments_resets_repeat_count(
        self,
    ) -> None:
        provider = MockProvider(
            [
                LLMResponse(
                    content=None,
                    tool_calls=(
                        ToolCall(
                            id=f"echo-{index}",
                            name="echo",
                            arguments={"text": "first"},
                        ),
                    ),
                )
                for index in range(1, 6)
            ]
            + [
                LLMResponse(
                    content=None,
                    tool_calls=(
                        ToolCall(
                            id="echo-different",
                            name="echo",
                            arguments={"text": "different"},
                        ),
                    ),
                )
            ]
            + [
                LLMResponse(
                    content=None,
                    tool_calls=(
                        ToolCall(
                            id=f"echo-{index}",
                            name="echo",
                            arguments={"text": "first"},
                        ),
                    ),
                )
                for index in range(6, 11)
            ]
            + [LLMResponse(content="done")]
        )
        session = Session(session_id="session-1")
        agent = Agent(
            provider=provider,
            session=session,
            system_prompt="You are helpful.",
            config=AGENT_CONFIG,
            workspace=TEST_WORKSPACE,
            now=lambda: REQUEST_TIME,
            tools=(EchoTool(),),
        )

        result = agent.run("repeat echo with different arguments in between")

        self.assertEqual(result.response.content, "done")
        self.assertEqual(len(provider.requests), 12)

    def test_argument_object_key_order_does_not_reset_repeat_count(
        self,
    ) -> None:
        provider = MockProvider(
            [
                LLMResponse(
                    content=None,
                    tool_calls=(
                        ToolCall(
                            id=f"call-{index}",
                            name="echo",
                            arguments=arguments,
                        ),
                    ),
                )
                for index, arguments in enumerate(
                    [
                        {"text": "hello", "extra": 1},
                        {"extra": 1, "text": "hello"},
                        {"text": "hello", "extra": 1},
                        {"extra": 1, "text": "hello"},
                        {"text": "hello", "extra": 1},
                        {"extra": 1, "text": "hello"},
                    ],
                    start=1,
                )
            ]
        )
        agent = Agent(
            provider=provider,
            session=Session(session_id="session-1"),
            system_prompt="You are helpful.",
            config=AGENT_CONFIG,
            workspace=TEST_WORKSPACE,
            now=lambda: REQUEST_TIME,
            tools=(EchoTool(),),
        )

        with self.assertRaises(ToolCallLimitExceededError):
            agent.run("repeat the exact same call")


if __name__ == "__main__":
    unittest.main()
