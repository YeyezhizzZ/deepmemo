from pathlib import Path
from types import SimpleNamespace

import pytest

import src.services.llm_service as llm_module
from src.services.llm_service import LLMConfigurationError, LLMService


def test_missing_config_is_reported_only_when_llm_is_called(tmp_path: Path):
    config_path = tmp_path / "missing.yaml"

    service = LLMService(config_path)

    assert service.client is None
    with pytest.raises(LLMConfigurationError, match="LLM 未配置"):
        service.chat([{"role": "user", "content": "hello"}])


def test_empty_config_returns_clear_error(tmp_path: Path):
    config_path = tmp_path / "llm.yaml"
    config_path.write_text("", encoding="utf-8")
    service = LLMService(config_path)

    with pytest.raises(LLMConfigurationError, match="配置为空或格式无效"):
        service.chat([{"role": "user", "content": "hello"}])


def test_recommended_config_is_loaded_lazily(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config_path = tmp_path / "llm.yaml"
    config_path.write_text(
        "\n".join(
            [
                "llm:",
                "  use: test_provider",
                "  test_provider:",
                '    api_key: "test-key"',
                '    api_base: "https://example.invalid/v1"',
                '    model: "test-model"',
                "    max_tokens: 321",
                "    temperature: 0.2",
            ]
        ),
        encoding="utf-8",
    )
    client_init_calls: list[dict] = []
    completion_calls: list[dict] = []
    expected_response = object()

    class FakeCompletions:
        def create(self, **kwargs):
            completion_calls.append(kwargs)
            return expected_response

    class FakeOpenAI:
        def __init__(self, **kwargs):
            client_init_calls.append(kwargs)
            self.chat = type("FakeChat", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr(llm_module, "OpenAI", FakeOpenAI)
    service = LLMService(config_path)

    assert client_init_calls == []
    response = service.chat([{"role": "user", "content": "hello"}])

    assert response is expected_response
    assert client_init_calls == [{"api_key": "test-key", "base_url": "https://example.invalid/v1"}]
    assert completion_calls == [
        {
            "model": "test-model",
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 321,
            "temperature": 0.2,
            "stream": False,
        }
    ]


def test_legacy_config_remains_supported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config_path = tmp_path / "llm.yaml"
    config_path.write_text(
        "\n".join(
            [
                "legacy_provider:",
                '  api_key: "test-key"',
                '  api_base: "https://example.invalid/v1"',
                '  model: "legacy-model"',
            ]
        ),
        encoding="utf-8",
    )

    class FakeCompletions:
        def create(self, **kwargs):
            return kwargs

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = type("FakeChat", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr(llm_module, "OpenAI", FakeOpenAI)
    response = LLMService(config_path).chat([])

    assert response["model"] == "legacy-model"


def test_embedding_model_is_explicit_and_loaded_lazily(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    config_path = tmp_path / "llm.yaml"
    config_path.write_text(
        "\n".join(
            [
                "llm:",
                "  use: test_provider",
                "  test_provider:",
                '    api_key: "test-key"',
                '    api_base: "https://example.invalid/v1"',
                '    model: "chat-model"',
                '    embedding_model: "embedding-model"',
            ]
        ),
        encoding="utf-8",
    )
    embedding_calls = []

    class FakeEmbeddings:
        def create(self, **kwargs):
            embedding_calls.append(kwargs)
            return SimpleNamespace(
                data=[
                    SimpleNamespace(embedding=[1.0, 0.0]),
                    SimpleNamespace(embedding=[0.0, 1.0]),
                ]
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.embeddings = FakeEmbeddings()

    monkeypatch.setattr(llm_module, "OpenAI", FakeOpenAI)
    vectors = LLMService(config_path).embed(["first", "second"])

    assert vectors == [[1.0, 0.0], [0.0, 1.0]]
    assert embedding_calls == [
        {"model": "embedding-model", "input": ["first", "second"]}
    ]
