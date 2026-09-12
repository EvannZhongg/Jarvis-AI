import unittest
from unittest.mock import patch

from agent_core import (
    LLMRequest,
    Message,
    TokenUsage,
    ToolCall,
    ToolDefinition,
)
from agent_core.providers import LiteLLMProvider


def chunk(
    content: str | None = None,
    tool_calls: list[dict] | None = None,
    usage: object | None = None,
) -> object:
    """Build a streamed chunk shaped like a LiteLLM delta."""
    delta = {"content": content, "tool_calls": tool_calls}
    choice = {"delta": delta, "finish_reason": None}
    return type(
        "Chunk",
        (),
        {"choices": [choice], "usage": usage},
    )()


USAGE = type(
    "Usage",
    (),
    {
        "prompt_tokens": 12,
        "completion_tokens": 5,
        "total_tokens": 17,
    },
)()


class LiteLLMProviderTest(unittest.TestCase):
    @patch("agent_core.providers.litellm_provider.token_counter")
    @patch("agent_core.providers.litellm_provider.completion")
    def test_passes_configured_model_url_key_and_output_limit(
        self,
        completion_mock,
        token_counter_mock,
    ) -> None:
        completion_mock.return_value = iter(
            [
                chunk(content="resp"),
                chunk(content="onse"),
                chunk(usage=USAGE),
            ]
        )
        provider = LiteLLMProvider(
            model="openai/test-model",
            base_url="https://example.com/v1",
            api_key="secret",
            max_context_tokens=1000,
        )

        request = LLMRequest(
            system_prompt="You are helpful.",
            messages=(Message(role="user", content="hello"),),
            max_output_tokens=100,
        )
        token_counter_mock.return_value = 12

        input_tokens = provider.count_input_tokens(request)
        deltas: list[str] = []
        response = provider.stream(request, deltas.append)

        self.assertEqual(input_tokens, 12)
        self.assertEqual(deltas, ["resp", "onse"])
        self.assertEqual(response.content, "response")
        self.assertEqual(
            response.usage,
            TokenUsage(
                input_tokens=12,
                output_tokens=5,
                total_tokens=17,
            ),
        )
        token_counter_mock.assert_called_once_with(
            model="openai/test-model",
            messages=[
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "hello"},
            ],
            tools=None,
        )
        completion_mock.assert_called_once_with(
            model="openai/test-model",
            base_url="https://example.com/v1",
            api_key="secret",
            messages=[
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "hello"},
            ],
            stream=True,
            stream_options={"include_usage": True},
            max_tokens=100,
        )

    @patch("agent_core.providers.litellm_provider.completion")
    def test_serializes_tools_and_parses_tool_calls(
        self,
        completion_mock,
    ) -> None:
        completion_mock.return_value = iter(
            [
                chunk(
                    tool_calls=[
                        {
                            "index": 0,
                            "id": "call-1",
                            "function": {
                                "name": "read_file",
                                "arguments": '{"path"',
                            },
                        }
                    ]
                ),
                chunk(
                    tool_calls=[
                        {
                            "index": 0,
                            "function": {"arguments": ': "README.md"}'},
                        }
                    ]
                ),
            ]
        )
        provider = LiteLLMProvider(
            model="openai/test-model",
            max_context_tokens=1000,
        )
        tool = ToolDefinition(
            name="read_file",
            description="Read a workspace file.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                },
            },
        )

        response = provider.stream(
            LLMRequest(
                system_prompt="You are helpful.",
                messages=(
                    Message(role="user", content="read README.md"),
                    Message(
                        role="assistant",
                        content=None,
                        reasoning="Inspect the file before answering.",
                        tool_calls=(
                            ToolCall(
                                id="previous-call",
                                name="read_file",
                                arguments={"path": "README.md"},
                            ),
                        ),
                    ),
                    Message(
                        role="tool",
                        content='{"ok": true}',
                        tool_call_id="previous-call",
                    ),
                ),
                tools=(tool,),
            ),
            lambda text: None,
        )

        self.assertEqual(
            response.tool_calls,
            (
                ToolCall(
                    id="call-1",
                    name="read_file",
                    arguments={"path": "README.md"},
                ),
            ),
        )
        completion_mock.assert_called_once_with(
            model="openai/test-model",
            base_url=None,
            api_key=None,
            messages=[
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "read README.md"},
                {
                    "role": "assistant",
                    "content": None,
                    "reasoning_content": "Inspect the file before answering.",
                    "tool_calls": [
                        {
                            "id": "previous-call",
                            "type": "function",
                            "function": {
                                "name": "read_file",
                                "arguments": '{"path": "README.md"}',
                            },
                        }
                    ],
                },
                {
                    "role": "tool",
                    "content": '{"ok": true}',
                    "tool_call_id": "previous-call",
                },
            ],
            stream=True,
            stream_options={"include_usage": True},
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "description": "Read a workspace file.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                            },
                        },
                    },
                }
            ],
        )

    @patch(
        "agent_core.providers.litellm_provider.token_counter",
        return_value=42,
    )
    def test_counts_tools_as_part_of_input(
        self,
        token_counter_mock,
    ) -> None:
        provider = LiteLLMProvider(
            model="openai/test-model",
            max_context_tokens=1000,
        )
        tool = ToolDefinition(
            name="read_file",
            description="Read a workspace file.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                },
            },
        )

        count = provider.count_input_tokens(
            LLMRequest(
                system_prompt="You are helpful.",
                messages=(Message(role="user", content="read it"),),
                tools=(tool,),
            )
        )

        self.assertEqual(count, 42)
        token_counter_mock.assert_called_once_with(
            model="openai/test-model",
            messages=[
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "read it"},
            ],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "description": "Read a workspace file.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                            },
                        },
                    },
                }
            ],
        )

    @patch("agent_core.providers.litellm_provider.get_model_info")
    def test_uses_litellm_context_limit_when_not_configured(
        self,
        get_model_info_mock,
    ) -> None:
        get_model_info_mock.return_value = {
            "max_input_tokens": 128000,
            "max_tokens": 8192,
        }

        provider = LiteLLMProvider(
            model="openai/test-model",
            base_url="https://example.com/v1",
        )

        self.assertEqual(provider.max_context_tokens, 128000)
        get_model_info_mock.assert_called_once_with(
            model="openai/test-model",
            api_base="https://example.com/v1",
        )

    @patch("agent_core.providers.litellm_provider.get_model_info")
    def test_configured_context_limit_skips_litellm_metadata(
        self,
        get_model_info_mock,
    ) -> None:
        provider = LiteLLMProvider(
            model="openai/test-model",
            max_context_tokens=64000,
        )

        self.assertEqual(provider.max_context_tokens, 64000)
        get_model_info_mock.assert_not_called()

    def test_rejects_invalid_configured_context_limit(self) -> None:
        with self.assertRaises(ValueError):
            LiteLLMProvider(
                model="openai/test-model",
                max_context_tokens=0,
            )

    @patch("agent_core.providers.litellm_provider.get_model_info")
    def test_requires_config_for_model_without_context_metadata(
        self,
        get_model_info_mock,
    ) -> None:
        get_model_info_mock.return_value = {
            "max_input_tokens": None,
            "max_tokens": None,
        }

        with self.assertRaises(ValueError):
            LiteLLMProvider(model="custom/model")


if __name__ == "__main__":
    unittest.main()
