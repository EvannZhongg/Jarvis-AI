from importlib.resources import files

from agent_core.workspace import Workspace


def load_system_prompt(workspace: Workspace) -> str:
    template = (
        files("agent_core.prompts")
        .joinpath("Soul.md")
        .read_text(encoding="utf-8")
    )
    workspace_value = f"{{{{{workspace.path}}}}}"
    return template.replace("{{workspace}}", workspace_value).strip()


def load_consolidator_prompt() -> str:
    return (
        files("agent_core.prompts")
        .joinpath("Consolidator.md")
        .read_text(encoding="utf-8")
        .strip()
    )


__all__ = ["load_consolidator_prompt", "load_system_prompt"]
