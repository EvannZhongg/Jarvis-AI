import json

from litellm import completion, get_model_info, token_counter

from agent_core.llm import LLMProvider, LLMRequest, LLMResponse, TokenUsage
from agent_core.session import Message
from agent_core.tools import ToolCall, ToolDefinition


class LiteLLMProvider(LLMProvider):
    def __init__(
        self,
        model: str,
        base_url: str | None = None,
        api_key: str | None = None,
        max_context_tokens: int | None = None,
    ) -> None:
        self._model = model
        self._base_url = base_url
        self._api_key = api_key
        if max_context_tokens is not None:
            if (
                isinstance(max_context_tokens, bool)
                or not isinstance(max_context_tokens, int)
                or max_context_tokens < 1
            ):
                raise ValueError(
                    "max_context_tokens must be a positive integer"
                )
            self._max_context_tokens = max_context_tokens
        else:
            self._max_context_tokens = _get_model_max_context_tokens(
                model,
                base_url,
            )

    @property
    def max_context_tokens(self) -> int:
        return self._max_context_tokens

    def count_input_tokens(self, request: LLMRequest) -> int:
        messages = _request_messages(request)
        tools = _request_tools(request)
        return token_counter(
            model=self._model,
            messages=messages,
            tools=tools or None,
        )

    def complete(self, request: LLMRequest) -> LLMResponse:
        arguments = dict(
            model=self._model,
            base_url=self._base_url,
            api_key=self._api_key,
            messages=_request_messages(request),
        )
        tools = _request_tools(request)
        if tools:
            arguments["tools"] = tools
        if request.max_output_tokens is not None:
            arguments["max_tokens"] = request.max_output_tokens

        response = completion(**arguments)
        response_message = response.choices[0].message
        usage = response.usage
        return LLMResponse(
            content=response_message.content,
            tool_calls=tuple(
                _parse_tool_call(tool_call)
                for tool_call in (
                    getattr(response_message, "tool_calls", None) or []
                )
            ),
            usage=TokenUsage(
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
            )
            if usage is not None
            else None,
        )


def _request_messages(request: LLMRequest) -> list[dict[str, object]]:
    return [
        {"role": "system", "content": request.system_prompt},
        *[_message_to_dict(message) for message in request.messages],
    ]


def _request_tools(request: LLMRequest) -> list[dict[str, object]]:
    return [_tool_definition_to_dict(tool) for tool in request.tools]


def _get_model_max_context_tokens(
    model: str,
    base_url: str | None,
) -> int:
    try:
        model_info = get_model_info(model=model, api_base=base_url)
    except Exception as error:
        raise ValueError(
            f"LiteLLM has no context limit metadata for model '{model}'; "
            "configure 'max_context_tokens' for this provider"
        ) from error

    max_context_tokens = model_info.get("max_input_tokens")
    if max_context_tokens is None:
        max_context_tokens = model_info.get("max_tokens")
    if (
        isinstance(max_context_tokens, bool)
        or not isinstance(max_context_tokens, int)
        or max_context_tokens < 1
    ):
        raise ValueError(
            f"LiteLLM has no context limit metadata for model '{model}'; "
            "configure 'max_context_tokens' for this provider"
        )
    return max_context_tokens


def _message_to_dict(message: Message) -> dict[str, object]:
    data: dict[str, object] = {
        "role": message.role,
        "content": message.content,
    }
    if message.tool_calls:
        data["tool_calls"] = [
            {
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.name,
                    "arguments": json.dumps(
                        tool_call.arguments,
                        ensure_ascii=False,
                    ),
                },
            }
            for tool_call in message.tool_calls
        ]
    if message.tool_call_id is not None:
        data["tool_call_id"] = message.tool_call_id
    return data


def _tool_definition_to_dict(tool: ToolDefinition) -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


def _parse_tool_call(value: object) -> ToolCall:
    tool_call_id = _get_field(value, "id")
    function = _get_field(value, "function")
    name = _get_field(function, "name")
    arguments = _get_field(function, "arguments")

    if not isinstance(tool_call_id, str) or not tool_call_id:
        raise ValueError("tool call id must be a non-empty string")
    if not isinstance(name, str) or not name:
        raise ValueError("tool call name must be a non-empty string")
    if isinstance(arguments, str):
        arguments = json.loads(arguments)
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise ValueError("tool call arguments must be a JSON object")

    return ToolCall(
        id=tool_call_id,
        name=name,
        arguments=arguments,
    )


def _get_field(value: object, name: str) -> object:
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)
