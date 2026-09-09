import unittest
from unittest.mock import patch

from agent_core import LLMRequest, Message, TokenUsage
from agent_core.providers import LiteLLMProvider


class ResponseMessage:
    content = "response"


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


if __name__ == "__main__":
    unittest.main()
