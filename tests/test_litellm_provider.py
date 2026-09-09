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


class ResponseMessage:
    content = "response"
    tool_calls = None


class ResponseChoice:
    message = ResponseMessage()


class CompletionResponse:
    choices = [ResponseChoice()]
    usage = type(
        "Usage",
        (),
        {
            "prompt_tokens": 12,
            "completion_tokens": 5,
            "total_tokens": 17,
        },
    )()


class LiteLLMProviderTest(unittest.TestCase):
    @patch(
        "agent_core.providers.litellm_provider.completion",
        return_value=CompletionResponse(),
    )
    def test_passes_configured_model_url_and_key(self, completion_mock) -> None:
        provider = LiteLLMProvider(
            model="openai/test-model",
            base_url="https://example.com/v1",
            api_key="secret",
        )

        response = provider.complete(
            LLMRequest(
                system_prompt="You are helpful.",
                messages=(Message(role="user", content="hello"),),
            )
        )

        self.assertEqual(response.content, "response")
        self.assertEqual(
            response.usage,
            TokenUsage(
                input_tokens=12,
                output_tokens=5,
                total_tokens=17,
            ),
        )
        completion_mock.assert_called_once_with(
            model="openai/test-model",
            base_url="https://example.com/v1",
            api_key="secret",
            messages=[
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "hello"},
            ],
        )

    @patch("agent_core.providers.litellm_provider.completion")
    def test_serializes_tools_and_parses_tool_calls(
        self,
        completion_mock,
    ) -> None:
        response_message = type(
            "ResponseMessage",
            (),
            {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "get_current_time",
                            "arguments": "{}",
                        },
                    }
                ],
            },
        )()
        completion_mock.return_value = type(
            "CompletionResponse",
            (),
            {
                "choices": [
                    type("ResponseChoice", (), {"message": response_message})()
                ],
                "usage": None,
            },
        )()
        provider = LiteLLMProvider(model="openai/test-model")
        tool = ToolDefinition(
            name="get_current_time",
            description="Get the current time.",
            parameters={
                "type": "object",
                "properties": {},
            },
        )

        response = provider.complete(
            LLMRequest(
                system_prompt="You are helpful.",
                messages=(
                    Message(role="user", content="what time is it?"),
                    Message(
                        role="assistant",
                        content=None,
                        tool_calls=(
                            ToolCall(
                                id="previous-call",
                                name="get_current_time",
                                arguments={},
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
            )
        )

        self.assertEqual(
            response.tool_calls,
            (
                ToolCall(
                    id="call-1",
                    name="get_current_time",
                    arguments={},
                ),
            ),
        )
        completion_mock.assert_called_once_with(
            model="openai/test-model",
            base_url=None,
            api_key=None,
            messages=[
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "what time is it?"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "previous-call",
                            "type": "function",
                            "function": {
                                "name": "get_current_time",
                                "arguments": "{}",
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
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "get_current_time",
                        "description": "Get the current time.",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                        },
                    },
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
