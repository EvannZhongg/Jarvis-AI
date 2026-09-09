from abc import ABC, abstractmethod
from dataclasses import dataclass

from .session import Message


@dataclass(frozen=True)
class LLMRequest:
    messages: tuple[Message, ...]


@dataclass(frozen=True)
class LLMResponse:
    content: str


class LLMProvider(ABC):
    @abstractmethod
    def complete(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError
