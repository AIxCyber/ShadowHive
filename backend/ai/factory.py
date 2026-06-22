from backend.ai.anthropic_provider import AnthropicProvider
from backend.ai.base import AIProvider, ProviderConfig
from backend.ai.ollama_provider import OllamaProvider
from backend.ai.openai_provider import OpenAIProvider

_PROVIDER_MAP = {
    "ollama": OllamaProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
}

_providers: dict[str, AIProvider] = {}


def create_provider(
    name: str,
    config: ProviderConfig,
) -> AIProvider:
    cls = _PROVIDER_MAP.get(name)
    if not cls:
        raise ValueError(f"Unknown provider: {name}. Available: {list(_PROVIDER_MAP.keys())}")
    return cls(config)


def get_provider(name: str) -> AIProvider | None:
    return _providers.get(name)


def register_provider(name: str, provider: AIProvider):
    _providers[name] = provider


def get_provider_for_module(
    module_name: str,
    global_config: dict,
) -> AIProvider:
    routing = global_config.get("ai", {}).get("routing", {})
    fallback_config = global_config.get("ai", {}).get("fallback", {})
    provider_name = routing.get(module_name, global_config.get("ai", {}).get("default_provider", "ollama"))
    provider = _providers.get(provider_name)
    if provider:
        return provider
    if fallback_config.get("enabled", False):
        for fallback_name in fallback_config.get("order", []):
            fb = _providers.get(fallback_name)
            if fb:
                return fb
    provider = _providers.get("ollama")
    if not provider:
        raise RuntimeError("No AI provider available — ensure Ollama is configured and running")
    return provider


_REQUIRES_API_KEY = {"openai", "anthropic"}


def init_providers(ai_config: dict):
    _providers.clear()
    for name, cfg in ai_config.get("providers", {}).items():
        api_key = _resolve_env(cfg.get("api_key", ""))
        if name in _REQUIRES_API_KEY and not api_key:
            continue
        provider_cfg = ProviderConfig(
            api_key=api_key,
            base_url=cfg.get("base_url"),
            default_model=cfg.get("default_model", ""),
            timeout=cfg.get("timeout", 60),
        )
        provider = create_provider(name, provider_cfg)
        _providers[name] = provider


def _resolve_env(value: str) -> str | None:
    import os

    if not value:
        return None
    if value.startswith("${") and value.endswith("}"):
        env_var = value[2:-1]
        result = os.getenv(env_var)
        return result if result else None
    return value
