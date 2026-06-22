import pytest

from backend.ai.base import ProviderConfig
from backend.ai.factory import create_provider


def test_ollama_provider_creation():
    config = ProviderConfig(base_url="http://localhost:11434", default_model="llama3.1:8b")
    provider = create_provider("ollama", config)
    assert provider.name == "ollama"
    assert provider.config.default_model == "llama3.1:8b"


def test_openai_provider_creation():
    config = ProviderConfig(api_key="sk-test", default_model="gpt-4o")
    provider = create_provider("openai", config)
    assert provider.name == "openai"


def test_anthropic_provider_creation():
    config = ProviderConfig(api_key="sk-test-anthropic", default_model="claude-sonnet-4-20250514")
    provider = create_provider("anthropic", config)
    assert provider.name == "anthropic"


def test_unknown_provider():
    config = ProviderConfig()
    with pytest.raises(ValueError, match="Unknown provider"):
        create_provider("nonexistent", config)
