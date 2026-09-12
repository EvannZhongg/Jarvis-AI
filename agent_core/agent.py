import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable, TypeAlias

from .config import AgentConfig
from .llm import LLMProvider, LLMRequest
from .llm import LLMResponse
from .prompts import load_consolidator_prompt
from .session import Message, Session
from .tool_result import ToolResultNormalizer
from .tools import Tool, ToolCall, ToolPolicy, ToolRegistry, ToolResult
from .workspace import Workspace


class ToolCallLimitExceededError(RuntimeError):
    def __init__(self, tool_name: str, limit: int) -> None:
        self.tool_name = tool_name
        self.limit = limit
        super().__init__(
            f"tool call '{tool_name}' exceeded the maximum of "
            f"{limit} identical consecutive executions"
        )


class ContextWindowExceededError(RuntimeError):
    def __init__(
        self,
        input_tokens: int,
        max_context_tokens: int,
        max_output_tokens: int,
    ) -> None:
        self.input_tokens = input_tokens
        self.max_context_tokens = max_context_tokens
        self.max_output_tokens = max_output_tokens
        self.max_input_tokens = max_context_tokens - max_output_tokens
        super().__init__(
            f"input context contains {input_tokens} tokens, exceeding the "
            f"maximum of {self.max_input_tokens} tokens "
            f"({max_context_tokens} context tokens minus "
            f"{max_output_tokens} reserved output tokens)"
        )


@dataclass(frozen=True)
class AgentRunResult:
    request: LLMRequest
    response: LLMResponse
    items: tuple[Message, ...]
    user_input: str
    request_timestamp_utc: datetime
    response_timestamp_utc: datetime


@dataclass(frozen=True)
class AssistantMessageDeltaEvent:
    text: str
    model_call_index: int


@dataclass(frozen=True)
class AssistantMessageEvent:
    content: str
    timestamp_utc: datetime
    model_call_index: int


@dataclass(frozen=True)
class ToolBatchStartedEvent:
    model_call_index: int
    tool_calls: tuple[ToolCall, ...]


@dataclass(frozen=True)
class ToolCallEvent:
    tool_call: ToolCall
    tool_index: int
    tool_count: int


@dataclass(frozen=True)
class ToolResultEvent:
    tool_result: ToolResult
    tool_index: int
    tool_count: int


@dataclass(frozen=True)
class ContextArchivedEvent:
    checkpoint_number: int


AgentEvent: TypeAlias = (
    AssistantMessageDeltaEvent
    | AssistantMessageEvent
    | ToolBatchStartedEvent
    | ToolCallEvent
    | ToolResultEvent
    | ContextArchivedEvent
)


class Agent:
    def __init__(
        self,
        provider: LLMProvider,
        session: Session,
        system_prompt: str,
        config: AgentConfig,
        workspace: Workspace,
        now: Callable[[], datetime] | None = None,
        tools: Iterable[Tool] = (),
        tool_policy: ToolPolicy | None = None,
        tool_result_normalizer: ToolResultNormalizer | None = None,
    ) -> None:
        self._provider = provider
        self._session = session
        self._workspace = workspace
        self._system_prompt = system_prompt
        self._config = config
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._tools = ToolRegistry(tools, policy=tool_policy)
        self._tool_result_normalizer = (
            tool_result_normalizer
            or ToolResultNormalizer(workspace, session.session_id)
        )
        if self._config.max_output_tokens >= self._provider.max_context_tokens:
            raise ValueError(
                "max_output_tokens must be less than the provider's "
                "max_context_tokens"
            )
        configured_budget = (
            self._provider.max_context_tokens
            - self._config.max_output_tokens
            - 1024
        )
        # A window smaller than the safety margin cannot be compressed; it
        # retains the regular provider hard-limit check below.
        self._compression_enabled = configured_budget > 0
        self._context_budget = configured_budget

    def run(
        self,
        user_input: str,
        on_event: Callable[[AgentEvent], None] | None = None,
    ) -> AgentRunResult:
        turn_start = len(self._session.items)
        model_call_index = 0
        previous_tool_call_key: tuple[str, str] | None = None
        identical_tool_calls = 0
        request_timestamp_utc = self._now().astimezone(timezone.utc)

        self._session.add_item(
            "user",
            user_input,
            timestamp_utc=request_timestamp_utc,
        )

        while True:
            request = self._build_request()
            input_tokens = self._provider.count_input_tokens(request)
            if self._compression_enabled and (
                input_tokens >= self._context_budget
                and self._archivable_items()
            ):
                checkpoint_number = self._archive_context()
                if on_event is not None:
                    on_event(ContextArchivedEvent(checkpoint_number))
                continue
            hard_limit = (
                self._context_budget
                if self._compression_enabled
                else self._provider.max_context_tokens
                - self._config.max_output_tokens
            )
            if input_tokens > hard_limit:
                raise ContextWindowExceededError(
                    input_tokens=input_tokens,
                    max_context_tokens=self._provider.max_context_tokens,
                    max_output_tokens=self._config.max_output_tokens,
                )
            model_call_index += 1

            def on_text_delta(
                text: str,
                model_call_index: int = model_call_index,
            ) -> None:
                if on_event is not None:
                    on_event(
                        AssistantMessageDeltaEvent(
                            text=text,
                            model_call_index=model_call_index,
                        )
                    )

            response = self._provider.stream(request, on_text_delta)

            if response.tool_calls:
                next_tool_call_key = previous_tool_call_key
                next_identical_calls = identical_tool_calls
                for tool_call in response.tool_calls:
                    tool_call_key = _tool_call_key(tool_call)
                    if tool_call_key == next_tool_call_key:
                        next_identical_calls += 1
                    else:
                        next_tool_call_key = tool_call_key
                        next_identical_calls = 1

                    if (
                        next_identical_calls
                        > self._config.max_same_tool_calls
                    ):
                        raise ToolCallLimitExceededError(
                            tool_call.name,
                            self._config.max_same_tool_calls,
                        )
                previous_tool_call_key = next_tool_call_key
                identical_tool_calls = next_identical_calls

                assistant_timestamp_utc = self._now().astimezone(timezone.utc)
                self._session.add_item(
                    role="assistant",
                    content=response.content,
                    timestamp_utc=assistant_timestamp_utc,
                    tool_calls=response.tool_calls,
                )
                if response.content and on_event is not None:
                    on_event(
                        AssistantMessageEvent(
                            content=response.content,
                            timestamp_utc=assistant_timestamp_utc,
                            model_call_index=model_call_index,
                        )
                    )
                if on_event is not None:
                    on_event(
                        ToolBatchStartedEvent(
                            model_call_index=model_call_index,
                            tool_calls=response.tool_calls,
                        )
                    )
                tool_count = len(response.tool_calls)
                for tool_index, tool_call in enumerate(
                    response.tool_calls,
                    start=1,
                ):
                    if on_event is not None:
                        on_event(
                            ToolCallEvent(
                                tool_call=tool_call,
                                tool_index=tool_index,
                                tool_count=tool_count,
                            )
                        )
                    tool_result = self._tools.execute(tool_call)
                    normalized_content = (
                        self._tool_result_normalizer.normalize(tool_result)
                    )
                    if on_event is not None:
                        on_event(
                            ToolResultEvent(
                                tool_result=tool_result,
                                tool_index=tool_index,
                                tool_count=tool_count,
                            )
                        )
                    self._session.add_item(
                        role="tool",
                        content=normalized_content,
                        timestamp_utc=self._now().astimezone(timezone.utc),
                        tool_call_id=tool_call.id,
                    )
                continue

            if response.content is None:
                raise ValueError(
                    "LLM response must contain content or tool calls"
                )

            response_timestamp_utc = self._now().astimezone(timezone.utc)
            self._session.add_item(
                "assistant",
                response.content,
                timestamp_utc=response_timestamp_utc,
            )
            if on_event is not None:
                on_event(
                    AssistantMessageEvent(
                        content=response.content,
                        timestamp_utc=response_timestamp_utc,
                        model_call_index=model_call_index,
                    )
                )
            return AgentRunResult(
                request=request,
                response=response,
                items=tuple(self._session.items[turn_start:]),
                user_input=user_input,
                request_timestamp_utc=request_timestamp_utc,
                response_timestamp_utc=response_timestamp_utc,
            )

    def _build_request(self) -> LLMRequest:
        system_prompt = self._system_prompt
        if self._session.archived_summary is not None:
            system_prompt = (
                f"{system_prompt}\n\n[Archived Context Summary]\n"
                f"{self._session.archived_summary}"
            )
        return LLMRequest(
            system_prompt=system_prompt,
            messages=tuple(
                _format_timed_message(item)
                for item in self._session.recent_items
            ),
            tools=self._tools.definitions,
            max_output_tokens=self._config.max_output_tokens,
        )

    def _archive_context(self) -> int:
        """Compress the unarchived transcript into the session checkpoint."""
        previous = self._session.archived_summary
        items = self._archivable_items()
        system_prompt = load_consolidator_prompt()
        if previous is not None:
            system_prompt = (
                f"{system_prompt}\n\n[Archived Context Summary]\n{previous}"
            )
        request = LLMRequest(
            system_prompt=system_prompt,
            messages=tuple(
                _format_timed_message(item)
                for item in items
            ),
            max_output_tokens=self._config.max_output_tokens,
        )
        response = self._provider.stream(request, lambda _text: None)
        summary = response.content.strip() if response.content else ""
        if response.tool_calls or not summary:
            raise ValueError("context consolidator must return text content")
        self._session.set_archived_summary(
            summary,
            self._session.archived_item_count + len(items),
        )
        return self._session.archived_item_count

    def _archivable_items(self) -> list[Message]:
        recent = self._session.recent_items
        # Keep the newest user turn explicit; it is the active question.
        if len(recent) > 1 and recent[-1].role == "user":
            return recent[:-1]
        return recent


def _tool_call_key(tool_call: ToolCall) -> tuple[str, str]:
    normalized_arguments = json.dumps(
        tool_call.arguments,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return tool_call.name, normalized_arguments


def _format_timed_message(message: Message) -> Message:
    content = message.content
    if (
        message.role != "tool"
        and message.timestamp_utc is not None
        and content is not None
    ):
        local_time = message.timestamp_utc.astimezone().isoformat(
            timespec="seconds"
        )
        content = f"[{local_time}] {content}"

    return Message(
        role=message.role,
        content=content,
        tool_calls=message.tool_calls,
        tool_call_id=message.tool_call_id,
    )
