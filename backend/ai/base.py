from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0


@dataclass
class ProviderConfig:
    api_key: str | None = None
    base_url: str | None = None
    default_model: str = ""
    timeout: int = 60
    extra: dict = field(default_factory=dict)


@dataclass
class ModelResponse:
    content: str
    model: str
    provider: str
    usage: TokenUsage = field(default_factory=TokenUsage)
    raw: dict | None = None


class AIProvider(ABC):
    name: str = ""
    config: ProviderConfig

    def __init__(self, config: ProviderConfig):
        self.config = config

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        on_token: Callable[[str], Coroutine] | None = None,
    ) -> ModelResponse: ...

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> ModelResponse: ...

    @abstractmethod
    async def embed(self, text: str, model: str | None = None) -> list[float]: ...
