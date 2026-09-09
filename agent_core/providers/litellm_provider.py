from litellm import completion

from agent_core.llm import LLMProvider, LLMRequest, LLMResponse, TokenUsage


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
                {"role": "system", "content": request.system_prompt},
                *[
                {"role": message.role, "content": message.content}
                for message in request.messages
                ],
            ],
        )
        usage = response.usage
        return LLMResponse(
            content=response.choices[0].message.content,
            usage=TokenUsage(
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
            )
            if usage is not None
            else None,
        )
