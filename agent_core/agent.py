import json
import inspect
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
class ReasoningDeltaEvent:
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
    | ReasoningDeltaEvent
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
        self._hard_limit = (
            self._provider.max_context_tokens
            - self._config.max_output_tokens
        )
        self._turn_start: int | None = None
        if self._hard_limit <= 1:
            raise ValueError(
                "max_context_tokens minus max_output_tokens must be greater "
                "than 1"
            )
        compression = self._config.context
        self._compression_enabled = compression.enabled
        trigger_ratio, target_ratio = _compression_ratios(
            self._provider.max_context_tokens,
            compression.trigger_ratio,
            compression.target_ratio,
        )
        self._compression_threshold = max(
            1, int(self._hard_limit * trigger_ratio)
        )
        self._compression_target = max(
            1, int(self._hard_limit * target_ratio)
        )
        if self._compression_enabled and (
            self._compression_target >= self._compression_threshold
            or self._compression_threshold >= self._hard_limit
        ):
            raise ValueError("compression target must be less than threshold")

    def run(
        self,
        user_input: str,
        on_event: Callable[[AgentEvent], None] | None = None,
    ) -> AgentRunResult:
        turn_start = len(self._session.items)
        self._turn_start = turn_start
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
                input_tokens >= self._compression_threshold
                and self._archivable_items(turn_start)
            ):
                checkpoint_number = self._archive_context(turn_start)
                if on_event is not None:
                    on_event(ContextArchivedEvent(checkpoint_number))
                continue
            if input_tokens > self._hard_limit:
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

            def on_reasoning_delta(text: str, model_call_index: int = model_call_index) -> None:
                if on_event is not None:
                    on_event(ReasoningDeltaEvent(text=text, model_call_index=model_call_index))

            if len(inspect.signature(self._provider.stream).parameters) >= 3:
                response = self._provider.stream(request, on_text_delta, on_reasoning_delta)
            else:
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
                    reasoning=response.reasoning,
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
                reasoning=response.reasoning,
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
            messages=tuple(self._context_messages()),
            tools=self._tools.definitions,
            max_output_tokens=self._config.max_output_tokens,
        )

    def _archive_context(self, turn_start: int) -> int:
        """Compress the unarchived transcript into the session checkpoint."""
        previous = self._session.archived_summary
        items = self._archivable_items(turn_start)
        system_prompt = load_consolidator_prompt()
        system_prompt = (
            f"{system_prompt}\n\nTarget checkpoint size: approximately "
            f"{self._compression_target} tokens."
        )
        if previous is not None:
            system_prompt = (
                f"{system_prompt}\n\n[Archived Context Summary]\n{previous}"
            )
        historical_items = [_historical_message(item) for item in items]
        timeline = _timeline_message(historical_items)
        request = LLMRequest(
            system_prompt=system_prompt,
            messages=tuple([timeline, *historical_items]),
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

    def _archivable_items(self, turn_start: int) -> list[Message]:
        """Return only complete turns preceding the active run.

        ``turn_start`` is captured before the current user message is added,
        so assistant/tool messages produced by the active model loop can
        never enter a checkpoint.
        """
        archive_start = self._session.archived_item_count
        archive_end = max(
            archive_start,
            min(turn_start, len(self._session.items)),
        )
        return self._session.items[archive_start:archive_end]

    def _context_messages(self) -> list[Message]:
        items = self._session.recent_items
        if self._turn_start is None:
            return list(items)
        historical_count = max(
            0,
            min(
                self._turn_start - self._session.archived_item_count,
                len(items),
            ),
        )
        historical = [
            _historical_message(item)
            for item in items[:historical_count]
        ]
        current = items[historical_count:]
        visible = historical + list(current)
        result: list[Message] = []
        for index, item in enumerate(visible):
            if item.role == "user":
                end = next(
                    (offset for offset in range(index + 1, len(visible))
                     if visible[offset].role == "user"),
                    len(visible),
                )
                result.append(_timeline_message(visible[index:end]))
            result.append(item)
        return result


def _historical_message(item: Message) -> Message:
    timestamp_utc = item.timestamp_utc
    if item.role == "tool" or (
        item.role == "assistant" and item.tool_calls
    ):
        timestamp_utc = None
    return Message(
        role=item.role,
        content=item.content,
        timestamp_utc=timestamp_utc,
        tool_calls=item.tool_calls,
        tool_call_id=item.tool_call_id,
        reasoning=None,
    )


def _timeline_message(items: list[Message]) -> Message:
    lines = []
    for item in items:
        if item.timestamp_utc is None:
            continue
        timestamp = item.timestamp_utc.astimezone().isoformat(timespec="seconds")
        detail = item.role
        if item.role == "assistant" and item.tool_calls:
            detail = "assistant step (" + ", ".join(
                call.name for call in item.tool_calls
            ) + ")"
        elif item.role == "tool":
            detail = f"tool result ({item.tool_call_id or 'unknown'})"
        lines.append(f"- {timestamp} — {detail}")
    return Message(
        role="system",
        content=(
            "[Conversation Timeline]\n"
            "Use these timestamps only to understand chronology and elapsed "
            "time. Do not reproduce them in responses.\n"
            + "\n".join(lines)
        ),
    )

def _compression_ratios(
    max_context_tokens: int,
    trigger_ratio: float | None,
    target_ratio: float | None,
) -> tuple[float, float]:
    """Resolve configured ratios or window-size defaults."""
    if max_context_tokens <= 32 * 1024:
        default_trigger, default_target = 0.75, 0.45
    elif max_context_tokens <= 256 * 1024:
        default_trigger, default_target = 0.80, 0.50
    else:
        # Keep active context bounded instead of scaling linearly with very
        # large model windows.
        default_trigger = 200_000 / max_context_tokens
        default_target = 128_000 / max_context_tokens
    return (
        trigger_ratio if trigger_ratio is not None else default_trigger,
        target_ratio if target_ratio is not None else default_target,
    )


def _tool_call_key(tool_call: ToolCall) -> tuple[str, str]:
    normalized_arguments = json.dumps(
        tool_call.arguments,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return tool_call.name, normalized_arguments
