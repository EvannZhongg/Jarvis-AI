import json
import os
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path


DEFAULT_CONFIG_FILENAMES = (
    "provider_config.json",
    "agent_config.json",
)


@dataclass(frozen=True)
class ModelConfig:
    model: str
    url: str | None
    key: str | None
    max_context_tokens: int | None = None


def default_config_directory() -> Path:
    return Path.home() / ".jarvis"


def initialize_default_configs(directory: Path) -> tuple[Path, ...]:
    created = []
    defaults = files("agent_cli.defaults")
    for filename in DEFAULT_CONFIG_FILENAMES:
        path = directory / filename
        if path.exists():
            continue
        directory.mkdir(parents=True, exist_ok=True)
        path.write_text(
            defaults.joinpath(filename).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        created.append(path)
    return tuple(created)


def load_config(path: Path) -> ModelConfig:
    with path.open(encoding="utf-8") as file:
        data = json.load(file)

    provider = data.get("provider")
    providers = data.get("providers")
    if not isinstance(provider, str) or not provider.strip():
        raise ValueError("config field 'provider' must be a non-empty string")
    provider = provider.strip()
    if not isinstance(providers, dict):
        raise ValueError("config field 'providers' must be an object")

    selected = providers.get(provider)
    if not isinstance(selected, dict):
        raise ValueError(f"provider '{provider}' is not configured")

    model = selected.get("model")
    if not isinstance(model, str) or not model.strip():
        raise ValueError(
            f"provider '{provider}' field 'model' must be a non-empty string"
        )

    url = _optional_string(selected, "url", provider)
    key = _optional_string(selected, "key", provider)
    max_context_tokens = _optional_positive_integer(
        selected,
        "max_context_tokens",
        provider,
    )
    if key and key.startswith("${") and key.endswith("}"):
        key_env = key[2:-1]
        if not key_env:
            raise ValueError(
                f"provider '{provider}' field 'key' has an empty "
                "environment variable reference"
            )
        key = os.environ.get(key_env)
        if not key:
            raise ValueError(
                f"environment variable '{key_env}' is required "
                f"for provider '{provider}'"
            )

    return ModelConfig(
        model=model.strip(),
        url=url,
        key=key,
        max_context_tokens=max_context_tokens,
    )


def _optional_string(
    data: dict[str, object],
    field: str,
    provider: str,
) -> str | None:
    value = data.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"provider '{provider}' field '{field}' must be a non-empty string"
        )
    return value.strip()


def _optional_positive_integer(
    data: dict[str, object],
    field: str,
    provider: str,
) -> int | None:
    value = data.get(field)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(
            f"provider '{provider}' field '{field}' must be a positive integer"
        )
    return value
