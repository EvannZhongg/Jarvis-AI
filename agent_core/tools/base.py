import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Iterable, Protocol, TypeAlias


JSONValue: TypeAlias = (
    str
    | int
    | float
    | bool
    | None
    | list["JSONValue"]
    | dict[str, "JSONValue"]
)


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, JSONValue]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, JSONValue]


@dataclass(frozen=True)
class ToolError:
    type: str
    message: str


@dataclass(frozen=True)
class ToolResult:
    tool_call_id: str
    name: str
    output: JSONValue = None
    error: ToolError | None = None

    def to_content(self) -> str:
        if self.error is not None:
            data: dict[str, JSONValue] = {
                "ok": False,
                "error": asdict(self.error),
            }
        else:
            data = {
                "ok": True,
                "output": self.output,
            }
        return json.dumps(data, ensure_ascii=False)


class Tool(ABC):
    @property
    @abstractmethod
    def definition(self) -> ToolDefinition:
        raise NotImplementedError

    @abstractmethod
    def execute(self, arguments: dict[str, JSONValue]) -> JSONValue:
        raise NotImplementedError


class ToolPolicy(Protocol):
    def authorize(self, call: ToolCall) -> None:
        raise NotImplementedError


class ToolRegistry:
    def __init__(
        self,
        tools: Iterable[Tool] = (),
        policy: ToolPolicy | None = None,
    ) -> None:
        self._tools: dict[str, Tool] = {}
        self._policy = policy
        for tool in tools:
            name = tool.definition.name
            if name in self._tools:
                raise ValueError(f"tool '{name}' is already registered")
            self._tools[name] = tool

    @property
    def definitions(self) -> tuple[ToolDefinition, ...]:
        return tuple(tool.definition for tool in self._tools.values())

    def execute(self, call: ToolCall) -> ToolResult:
        tool = self._tools.get(call.name)
        if tool is None:
            return ToolResult(
                tool_call_id=call.id,
                name=call.name,
                error=ToolError(
                    type="tool_not_found",
                    message=f"tool '{call.name}' is not registered",
                ),
            )

        try:
            if self._policy is not None:
                self._policy.authorize(call)
            output = tool.execute(call.arguments)
        except Exception as error:
            return ToolResult(
                tool_call_id=call.id,
                name=call.name,
                error=ToolError(
                    type=type(error).__name__,
                    message=str(error),
                ),
            )

        return ToolResult(
            tool_call_id=call.id,
            name=call.name,
            output=output,
        )
