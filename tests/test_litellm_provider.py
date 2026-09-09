import unittest
from unittest.mock import patch

from agent_core import LLMRequest, Message
from agent_core.providers import LiteLLMProvider


class ResponseMessage:
    content = "response"


class ResponseChoice:
    message = ResponseMessage()


class CompletionResponse:
    choices = [ResponseChoice()]


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
                messages=(Message(role="user", content="hello"),),
            )
        )

        self.assertEqual(response.content, "response")
        completion_mock.assert_called_once_with(
            model="openai/test-model",
            base_url="https://example.com/v1",
            api_key="secret",
            messages=[{"role": "user", "content": "hello"}],
        )


if __name__ == "__main__":
    unittest.main()
