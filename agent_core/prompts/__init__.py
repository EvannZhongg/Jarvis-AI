from importlib.resources import files


def load_system_prompt() -> str:
    return (
        files("agent_core.prompts")
        .joinpath("Soul.md")
        .read_text(encoding="utf-8")
        .strip()
    )


__all__ = ["load_system_prompt"]
