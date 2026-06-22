from collections.abc import Callable, Coroutine

from openai import AsyncOpenAI

from backend.ai.base import AIProvider, ModelResponse, ProviderConfig, TokenUsage


class OpenAIProvider(AIProvider):
    name = "openai"

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        kwargs = {
            "api_key": config.api_key,
            "timeout": config.timeout,
        }
        if config.base_url:
            kwargs["base_url"] = config.base_url
        self._client = AsyncOpenAI(**kwargs)

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        on_token: Callable[[str], Coroutine] | None = None,
    ) -> ModelResponse:
        model = model or self.config.default_model or "gpt-4o"
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        resp = await self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        choice = resp.choices[0]
        usage_data = resp.usage
        usage = TokenUsage(
            prompt_tokens=usage_data.prompt_tokens if usage_data else 0,
            completion_tokens=usage_data.completion_tokens if usage_data else 0,
            total_tokens=usage_data.total_tokens if usage_data else 0,
        )
        return ModelResponse(
            content=choice.message.content or "",
            model=model,
            provider=self.name,
            usage=usage,
            raw=resp.model_dump() if hasattr(resp, "model_dump") else None,
        )

    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> ModelResponse:
        model = model or self.config.default_model or "gpt-4o"
        resp = await self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        choice = resp.choices[0]
        usage_data = resp.usage
        usage = TokenUsage(
            prompt_tokens=usage_data.prompt_tokens if usage_data else 0,
            completion_tokens=usage_data.completion_tokens if usage_data else 0,
            total_tokens=usage_data.total_tokens if usage_data else 0,
        )
        return ModelResponse(
            content=choice.message.content or "",
            model=model,
            provider=self.name,
            usage=usage,
            raw=resp.model_dump() if hasattr(resp, "model_dump") else None,
        )

    async def embed(self, text: str, model: str | None = None) -> list[float]:
        model = model or "text-embedding-3-small"
        resp = await self._client.embeddings.create(model=model, input=text)
        return resp.data[0].embedding

    async def close(self):
        await self._client.close()
