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
                            "name": "read_file",
                            "arguments": '{"path": "README.md"}',
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
            name="read_file",
            description="Read a workspace file.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                },
            },
        )

        response = provider.complete(
            LLMRequest(
                system_prompt="You are helpful.",
                messages=(
                    Message(role="user", content="read README.md"),
                    Message(
                        role="assistant",
                        content=None,
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
            )
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


if __name__ == "__main__":
    unittest.main()
