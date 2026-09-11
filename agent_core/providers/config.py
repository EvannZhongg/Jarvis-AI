import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelConfig:
    model: str
    url: str | None
    key: str | None
    max_context_tokens: int | None = None


def _read_config(path: Path) -> tuple[str, dict]:
    with path.open(encoding="utf-8") as file:
        data = json.load(file)

    provider = data.get("provider")
    providers = data.get("providers")
    if not isinstance(provider, str) or not provider.strip():
        raise ValueError("config field 'provider' must be a non-empty string")
    provider = provider.strip()
    if not isinstance(providers, dict):
        raise ValueError("config field 'providers' must be an object")
    if provider not in providers:
        raise ValueError(f"provider '{provider}' is not configured")
    return provider, providers


def _model_name(selected: object, provider: str) -> str:
    if not isinstance(selected, dict):
        raise ValueError(f"provider '{provider}' is not configured")

    model = selected.get("model")
    if not isinstance(model, str) or not model.strip():
        raise ValueError(
            f"provider '{provider}' field 'model' must be a non-empty string"
        )
    return model.strip()


def load_model_options(path: Path) -> tuple[str, dict[str, str]]:
    default, providers = _read_config(path)
    return default, {
        name: _model_name(selected, name)
        for name, selected in providers.items()
    }


def load_config(path: Path, provider: str | None = None) -> ModelConfig:
    default, providers = _read_config(path)
    provider = default if provider is None else provider
    selected = providers.get(provider)
    model = _model_name(selected, provider)

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
