from collections.abc import Callable, Coroutine

from anthropic import AsyncAnthropic

from backend.ai.base import AIProvider, ModelResponse, ProviderConfig, TokenUsage


class AnthropicProvider(AIProvider):
    name = "anthropic"

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        kwargs = {
            "api_key": config.api_key,
            "timeout": config.timeout,
        }
        if config.base_url:
            kwargs["base_url"] = config.base_url
        self._client = AsyncAnthropic(**kwargs)

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        on_token: Callable[[str], Coroutine] | None = None,
    ) -> ModelResponse:
        model = model or self.config.default_model or "claude-sonnet-4-20250514"
        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system

        resp = await self._client.messages.create(**kwargs)
        usage = TokenUsage(
            prompt_tokens=resp.usage.input_tokens if resp.usage else 0,
            completion_tokens=resp.usage.output_tokens if resp.usage else 0,
            total_tokens=((resp.usage.input_tokens + resp.usage.output_tokens) if resp.usage else 0),
        )
        return ModelResponse(
            content=resp.content[0].text if resp.content else "",
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
        model = model or self.config.default_model or "claude-sonnet-4-20250514"
        system = None
        chat_messages = messages
        if messages and messages[0].get("role") == "system":
            system = messages[0]["content"]
            chat_messages = messages[1:]

        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": chat_messages,
        }
        if system:
            kwargs["system"] = system

        resp = await self._client.messages.create(**kwargs)
        usage = TokenUsage(
            prompt_tokens=resp.usage.input_tokens if resp.usage else 0,
            completion_tokens=resp.usage.output_tokens if resp.usage else 0,
            total_tokens=((resp.usage.input_tokens + resp.usage.output_tokens) if resp.usage else 0),
        )
        return ModelResponse(
            content=resp.content[0].text if resp.content else "",
            model=model,
            provider=self.name,
            usage=usage,
            raw=resp.model_dump() if hasattr(resp, "model_dump") else None,
        )

    async def embed(self, text: str, model: str | None = None) -> list[float]:
        await self._client.messages.create(
            model=model or "claude-sonnet-4-20250514",
            max_tokens=1,
            messages=[{"role": "user", "content": f"Embed this: {text}"}],
        )
        return [0.0]

    async def close(self):
        await self._client.close()
