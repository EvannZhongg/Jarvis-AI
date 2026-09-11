"""Agent runtime driven over newline-delimited JSON.

The TUI spawns this as a child process and exchanges protocol messages
on stdin/stdout. The class is kept free of process-level setup so tests
can drive it with plain string buffers.
"""

import json
from collections import deque
from itertools import count
from pathlib import Path
from typing import TextIO

from dotenv import load_dotenv

from agent_core import (
    Agent,
    JsonlSessionStore,
    Session,
    ShellApprovalPolicy,
    SubprocessCommandExecutor,
    Workspace,
    create_tools,
    load_agent_config,
)
from agent_core.prompts import load_system_prompt
from agent_core.providers import LiteLLMProvider

from .config import load_config
from .protocol import decode, encode, event_to_message, usage_to_dict


class Cancelled(Exception):
    """Raised to unwind the agent loop when a turn is cancelled."""


class Bridge:
    def __init__(self, stdin: TextIO, stdout: TextIO) -> None:
        self._stdin = stdin
        self._stdout = stdout
        self._deferred: deque[dict[str, object]] = deque()
        self._approval_ids = count(1)
        self._turn_id: str | None = None
        self._agent: Agent | None = None
        self._session: Session | None = None
        self._store: JsonlSessionStore | None = None

    def emit(self, type: str, **fields: object) -> None:
        self._stdout.write(encode({"type": type, **fields}) + "\n")

    def read_message(self) -> dict[str, object] | None:
        """Return the next protocol message, or None at end of input.

        Messages deferred by a nested approval read are replayed first,
        in arrival order.
        """
        if self._deferred:
            return self._deferred.popleft()
        return self._read_incoming()

    def _read_incoming(self) -> dict[str, object] | None:
        """Read a fresh message from stdin, skipping blank lines."""
        while True:
            line = self._stdin.readline()
            if not line:
                return None
            stripped = line.strip()
            if stripped:
                return decode(stripped)

    def request_permission(self, command: str) -> bool:
        request_id = f"{self._turn_id}:{next(self._approval_ids)}"
        self.emit(
            "approval_request",
            turn_id=self._turn_id,
            request_id=request_id,
            command=command,
        )
        while True:
            # Read fresh input only: replaying the deferred queue here
            # would spin, since non-matching messages go back onto it.
            message = self._read_incoming()
            if message is None or message["type"] == "shutdown":
                # The UI is gone; never run an unapproved command.
                raise Cancelled
            if (
                message["type"] == "approval_response"
                and message.get("request_id") == request_id
            ):
                return bool(message.get("approved"))
            self._deferred.append(message)

    def start(self, message: dict[str, object]) -> None:
        config_path = Path(str(message["provider_config_path"]))
        agent_config_path = Path(str(message["agent_config_path"]))
        load_dotenv(config_path.parent / ".env")

        workspace = Workspace(Path(str(message["workspace"])))
        provider = message.get("provider")
        config = load_config(
            config_path,
            provider if isinstance(provider, str) and provider else None,
        )
        agent_config = load_agent_config(agent_config_path)

        session_id = message.get("session_id")
        self._store = JsonlSessionStore(workspace.path / "sessions")
        resumed = isinstance(session_id, str) and bool(session_id)
        self._session = (
            self._store.load(str(session_id)) if resumed else Session()
        )

        self._agent = Agent(
            provider=LiteLLMProvider(
                model=config.model,
                base_url=config.url,
                api_key=config.key,
                max_context_tokens=config.max_context_tokens,
            ),
            session=self._session,
            system_prompt=load_system_prompt(workspace),
            config=agent_config,
            workspace=workspace,
            tools=create_tools(
                agent_config.tools,
                workspace,
                SubprocessCommandExecutor(workspace.path),
                shell_timeout_seconds=agent_config.shell_timeout_seconds,
            ),
            tool_policy=ShellApprovalPolicy(self.request_permission),
        )

        self.emit(
            "ready",
            session_id=self._session.session_id,
            workspace=str(workspace.path),
            model=config.model,
            resumed=resumed,
            message_count=len(self._session.items),
        )

    def run_turn(self, message: dict[str, object]) -> None:
        if self._agent is None or self._session is None or self._store is None:
            raise RuntimeError("received 'user_turn' before 'start'")

        self._turn_id = str(message["turn_id"])
        try:
            result = self._agent.run(
                str(message["text"]),
                on_event=lambda event: self.emit(
                    **event_to_message(event, self._turn_id or "")
                ),
            )
        except (KeyboardInterrupt, Cancelled):
            # Without an AgentRunResult there is nothing to append, so
            # the partial turn stays in memory only.
            self.emit(
                "turn_cancelled",
                turn_id=self._turn_id,
                persisted=False,
            )
            return
        except Exception as error:
            self.emit(
                "turn_failed",
                turn_id=self._turn_id,
                error={
                    "type": type(error).__name__,
                    "message": str(error),
                },
            )
            return

        self._store.append_turn(
            self._session.session_id,
            result.request,
            result.response,
            result.items,
        )
        self.emit(
            "turn_completed",
            turn_id=self._turn_id,
            usage=usage_to_dict(result.response.usage),
        )

    def serve(self) -> None:
        while True:
            try:
                message = self.read_message()
            except (json.JSONDecodeError, ValueError) as error:
                self.emit(
                    "fatal",
                    error={"type": "ProtocolError", "message": str(error)},
                )
                raise SystemExit(1)
            except KeyboardInterrupt:
                continue  # Interrupted while idle: nothing to cancel.

            if message is None or message["type"] == "shutdown":
                return
            if message["type"] == "start":
                self.start(message)
            elif message["type"] == "user_turn":
                self.run_turn(message)
