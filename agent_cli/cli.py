import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from agent_core import (
    Agent,
    AgentEvent,
    AssistantMessageEvent,
    JsonlSessionStore,
    Session,
    ShellApprovalPolicy,
    SubprocessCommandExecutor,
    ToolBatchStartedEvent,
    ToolCallEvent,
    ToolResultEvent,
    Workspace,
    create_tools,
    load_agent_config,
)
from agent_core.prompts import load_system_prompt
from agent_core.providers import LiteLLMProvider

from .config import load_config


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "provider_config.json"
DEFAULT_AGENT_CONFIG_PATH = PROJECT_ROOT / "agent_config.json"
DEFAULT_SESSION_STORE_PATH = PROJECT_ROOT / "sessions.jsonl"
TIMESTAMP_PREFIX = re.compile(
    r"^\[\d{4}-\d{2}-\d{2}T[^\]]+\]\s*"
)


def print_assistant_message(
    content: str,
    timestamp_utc: datetime,
    model_call_index: int,
) -> None:
    display_content = TIMESTAMP_PREFIX.sub("", content, count=1)
    if not display_content:
        return

    local_time = timestamp_utc.astimezone().isoformat(timespec="seconds")
    print(f"\nAssistant · model call #{model_call_index} [{local_time}]")
    print(display_content)


def print_agent_event(event: AgentEvent) -> None:
    if isinstance(event, AssistantMessageEvent):
        print_assistant_message(
            event.content,
            event.timestamp_utc,
            event.model_call_index,
        )
        return

    if isinstance(event, ToolBatchStartedEvent):
        print(
            f"\nTools · model call #{event.model_call_index} "
            f"· {len(event.tool_calls)} call(s)"
        )
        return

    if isinstance(event, ToolCallEvent):
        arguments = json.dumps(
            event.tool_call.arguments,
            ensure_ascii=False,
            sort_keys=True,
        )
        print(
            f"  [{event.tool_index}/{event.tool_count}] → "
            f"{event.tool_call.name} {arguments}"
        )
        return

    result = event.tool_result
    if result.error is None:
        print("        ✓ completed")
    else:
        print(
            "        ✗ failed: "
            f"{result.error.type}: {result.error.message}"
        )


def request_shell_permission(command: str) -> bool:
    print("\nShell command requires approval:")
    print(command)
    try:
        response = input("Allow this command? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return response.strip().lower() in {"y", "yes"}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="jarvis")
    parser.add_argument(
        "--workspace",
        type=Path,
        default=None,
        help="Workspace directory. Defaults to the current directory.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to the JSON model configuration.",
    )
    parser.add_argument(
        "--agent-config",
        type=Path,
        default=DEFAULT_AGENT_CONFIG_PATH,
        help="Path to the JSON agent behavior configuration.",
    )
    parser.add_argument(
        "--session",
        help="Existing session id to resume. A new id is created when omitted.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    load_dotenv(PROJECT_ROOT / ".env")

    try:
        workspace = Workspace(args.workspace or Path.cwd())
        config = load_config(args.config)
        agent_config = load_agent_config(args.agent_config)
    except (OSError, ValueError) as error:
        raise SystemExit(f"Failed to start Jarvis: {error}") from error

    store = JsonlSessionStore(DEFAULT_SESSION_STORE_PATH)
    session = store.load(args.session) if args.session else Session()
    command_executor = SubprocessCommandExecutor(workspace.path)
    agent = Agent(
        provider=LiteLLMProvider(
            model=config.model,
            base_url=config.url,
            api_key=config.key,
            max_context_tokens=config.max_context_tokens,
        ),
        session=session,
        system_prompt=load_system_prompt(workspace),
        config=agent_config,
        workspace=workspace,
        tools=create_tools(
            agent_config.tools,
            workspace,
            command_executor,
        ),
        tool_policy=ShellApprovalPolicy(request_shell_permission),
    )

    print(f"Session: {session.session_id}")
    print(f"Workspace: {workspace.path}")

    while True:
        try:
            user_input = input("> ")
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if user_input.strip().lower() in {"exit", "quit"}:
            return
        if not user_input.strip():
            continue

        result = agent.run(user_input, on_event=print_agent_event)
        store.append_turn(
            session.session_id,
            result.request,
            result.response,
            result.items,
        )
