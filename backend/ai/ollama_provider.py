import asyncio
import json
from collections.abc import Callable, Coroutine

import httpx

from backend.ai.base import AIProvider, ModelResponse, ProviderConfig, TokenUsage


class OllamaProvider(AIProvider):
    name = "ollama"

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.base_url = config.base_url or "http://localhost:11434"
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(6000.0, connect=30.0))
        self._semaphore = asyncio.Semaphore(1)

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        on_token: Callable[[str], Coroutine] | None = None,
    ) -> ModelResponse:
        model = model or self.config.default_model or "llama3.1:8b"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if system:
            payload["system"] = system

        content_parts: list[str] = []
        usage = TokenUsage()

        async with self._semaphore:
            async with self._client.stream("POST", f"{self.base_url}/api/generate", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    token = chunk.get("response", "")
                    if token:
                        content_parts.append(token)
                        if on_token:
                            await on_token(token)
                    if chunk.get("done"):
                        usage = TokenUsage(
                            prompt_tokens=chunk.get("prompt_eval_count", 0),
                            completion_tokens=chunk.get("eval_count", 0),
                            total_tokens=(chunk.get("prompt_eval_count", 0) + chunk.get("eval_count", 0)),
                        )
                        break

        return ModelResponse(
            content="".join(content_parts),
            model=model,
            provider=self.name,
            usage=usage,
            raw=None,
        )

    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> ModelResponse:
        model = model or self.config.default_model or "llama3.1:8b"
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        content_parts: list[str] = []
        usage = TokenUsage()

        async with self._semaphore:
            async with self._client.stream("POST", f"{self.base_url}/api/chat", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    token = chunk.get("message", {}).get("content", "")
                    if token:
                        content_parts.append(token)
                    if chunk.get("done"):
                        usage = TokenUsage(
                            prompt_tokens=chunk.get("prompt_eval_count", 0),
                            completion_tokens=chunk.get("eval_count", 0),
                            total_tokens=(chunk.get("prompt_eval_count", 0) + chunk.get("eval_count", 0)),
                        )
                        break

        return ModelResponse(
            content="".join(content_parts),
            model=model,
            provider=self.name,
            usage=usage,
            raw=None,
        )

    async def generate_embedding(
        self,
        text: str,
        model: str | None = None,
    ) -> list[float]:
        """Generate an embedding vector for the given text."""
        model = model or "nomic-embed-text"
        payload = {"model": model, "prompt": text}
        resp = await self._client.post(
            f"{self.base_url}/api/embeddings",
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("embedding", [])

    async def embed(self, text: str, model: str | None = None) -> list[float]:
        return await self.generate_embedding(text, model)

    async def close(self):
        await self._client.aclose()
