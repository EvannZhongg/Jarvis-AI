import argparse
from pathlib import Path

from dotenv import load_dotenv

from agent_core import Agent, GetCurrentTimeTool, JsonlSessionStore, Session
from agent_core.prompts import load_system_prompt
from agent_core.providers import LiteLLMProvider

from .config import load_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("provider_config.json"),
        help="Path to the JSON model configuration.",
    )
    parser.add_argument(
        "--session",
        help="Existing session id to resume. A new id is created when omitted.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_dotenv()

    try:
        config = load_config(args.config)
    except (OSError, ValueError) as error:
        raise SystemExit(f"Failed to load config: {error}") from error

    store = JsonlSessionStore(Path("sessions.jsonl"))
    session = store.load(args.session) if args.session else Session()
    agent = Agent(
        provider=LiteLLMProvider(
            model=config.model,
            base_url=config.url,
            api_key=config.key,
        ),
        session=session,
        system_prompt=load_system_prompt(),
        tools=(GetCurrentTimeTool(),),
    )

    print(f"Session: {session.session_id}")

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

        result = agent.run(user_input)
        store.append_turn(
            session.session_id,
            result.request,
            result.response,
            result.items,
        )
        local_time = result.response_timestamp_utc.astimezone().isoformat(
            timespec="seconds"
        )
        print(f"Assistant [{local_time}]: {result.response.content}")


if __name__ == "__main__":
    main()
