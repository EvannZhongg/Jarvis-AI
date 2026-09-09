from litellm import completion

from agent_core.llm import LLMProvider, LLMRequest, LLMResponse


class LiteLLMProvider(LLMProvider):
    def __init__(
        self,
        model: str,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self._model = model
        self._base_url = base_url
        self._api_key = api_key

    def complete(self, request: LLMRequest) -> LLMResponse:
        response = completion(
            model=self._model,
            base_url=self._base_url,
            api_key=self._api_key,
            messages=[
                {"role": message.role, "content": message.content}
                for message in request.messages
            ],
        )
        return LLMResponse(content=response.choices[0].message.content)
