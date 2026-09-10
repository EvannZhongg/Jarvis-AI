import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_cli.config import ModelConfig, load_config


class ConfigTest(unittest.TestCase):
    def test_loads_selected_provider_from_json_and_env(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "provider": "deepseek",
                        "providers": {
                            "openai": {
                                "model": "openai/test-model",
                                "key": "${OPENAI_KEY}",
                            },
                            "deepseek": {
                                "model": "deepseek/test-model",
                                "url": "https://example.com",
                                "key": "${DEEPSEEK_KEY}",
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(
                "os.environ",
                {"DEEPSEEK_KEY": "secret"},
                clear=True,
            ):
                self.assertEqual(
                    load_config(path),
                    ModelConfig(
                        model="deepseek/test-model",
                        url="https://example.com",
                        key="secret",
                        max_context_tokens=None,
                    ),
                )

    def test_strips_whitespace_from_provider_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "provider": " test ",
                        "providers": {
                            "test": {
                                "model": " openai/test-model ",
                                "url": " https://example.com/v1 ",
                                "key": " secret ",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                load_config(path),
                ModelConfig(
                    model="openai/test-model",
                    url="https://example.com/v1",
                    key="secret",
                    max_context_tokens=None,
                ),
            )

    def test_allows_inline_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "provider": "local",
                        "providers": {
                            "local": {
                                "model": "openai/local-model",
                                "url": "http://localhost:8000/v1",
                                "key": "local-key",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                load_config(path),
                ModelConfig(
                    model="openai/local-model",
                    url="http://localhost:8000/v1",
                    key="local-key",
                    max_context_tokens=None,
                ),
            )

    def test_loads_optional_provider_context_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "provider": "test",
                        "providers": {
                            "test": {
                                "model": "openai/test-model",
                                "max_context_tokens": 128000,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                load_config(path),
                ModelConfig(
                    model="openai/test-model",
                    url=None,
                    key=None,
                    max_context_tokens=128000,
                ),
            )

    def test_rejects_boolean_provider_context_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "provider": "test",
                        "providers": {
                            "test": {
                                "model": "openai/test-model",
                                "max_context_tokens": True,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                load_config(path)

    def test_rejects_unknown_selected_provider(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "provider": "missing",
                        "providers": {},
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                load_config(path)

    def test_rejects_missing_key_environment_variable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "provider": "test",
                        "providers": {
                            "test": {
                                "model": "test/model",
                                "key": "${TEST_KEY}",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict("os.environ", {}, clear=True):
                with self.assertRaises(ValueError):
                    load_config(path)


if __name__ == "__main__":
    unittest.main()
