from abc import ABC, abstractmethod
from dataclasses import dataclass

from .session import Message
from .tools import ToolCall, ToolDefinition


@dataclass(frozen=True)
class LLMRequest:
    system_prompt: str
    messages: tuple[Message, ...]
    tools: tuple[ToolDefinition, ...] = ()


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


@dataclass(frozen=True)
class LLMResponse:
    content: str | None
    tool_calls: tuple[ToolCall, ...] = ()
    usage: TokenUsage | None = None


class LLMProvider(ABC):
    @abstractmethod
    def complete(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError
