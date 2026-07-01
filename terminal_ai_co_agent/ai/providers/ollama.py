"""Ollama AI provider implementation."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, AsyncIterator, ClassVar

import httpx

from terminal_ai_co_agent.ai.provider import BaseAIProvider
from terminal_ai_co_agent.ai.types import (
    CompletionRequest,
    CompletionResponse,
    Message,
    MessageRole,
    ModelInfo,
    ModelRole,
    UsageInfo,
)

if TYPE_CHECKING:
    pass


class OllamaProvider(BaseAIProvider):
    """Provider for Ollama (local model runner)."""

    provider_name: ClassVar[str] = "ollama"
    default_model: ClassVar[str] = "qwen2.5:1.5b"

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11434",
        api_key: str | None = None,
        timeout: float = 120.0,
        retry_attempts: int = 3,
        retry_delay: float = 1.0,
    ) -> None:
        super().__init__(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            retry_attempts=retry_attempts,
            retry_delay=retry_delay,
        )
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Lazy-initialized HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
            )
        return self._client

    @property
    async def available_models(self) -> list[ModelInfo]:
        """Fetch available models from Ollama."""
        try:
            response = await self.client.get("/api/tags")
            response.raise_for_status()
            data = response.json()

            models: list[ModelInfo] = []
            for model_data in data.get("models", []):
                name = model_data["name"]
                details = model_data.get("details", {})
                models.append(
                    ModelInfo(
                        name=name,
                        provider=self.provider_name,
                        context_window=4096,  # Ollama doesn't expose this easily
                        max_tokens=4096,
                        metadata={
                            "size": model_data.get("size", 0),
                            "parameter_size": details.get("parameter_size", ""),
                            "quantization": details.get("quantization_level", ""),
                            "family": details.get("family", ""),
                        },
                    )
                )
            return models
        except Exception:
            return []

    async def health_check(self) -> bool:
        """Check if Ollama is reachable."""
        try:
            response = await self.client.get("/api/tags")
            return response.status_code == 200
        except Exception:
            return False

    async def _complete_impl(
        self,
        request: CompletionRequest,
    ) -> CompletionResponse:
        """Send a completion request to Ollama."""
        payload = {
            "model": request.model,
            "messages": [
                {"role": m.role.value, "content": m.content}
                for m in request.messages
            ],
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
                "top_p": request.top_p,
            },
        }

        if request.stop:
            payload["options"]["stop"] = request.stop

        response = await self.client.post("/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()

        return CompletionResponse(
            content=data["message"]["content"],
            model=data.get("model", request.model),
            usage=UsageInfo(
                prompt_tokens=data.get("prompt_eval_count", 0),
                completion_tokens=data.get("eval_count", 0),
                total_tokens=data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
            ),
            finish_reason=data.get("done_reason", "stop"),
            raw=data,
        )

    async def _stream_impl(
        self,
        request: CompletionRequest,
    ) -> AsyncIterator[str]:
        """Stream completion tokens from Ollama."""
        payload = {
            "model": request.model,
            "messages": [
                {"role": m.role.value, "content": m.content}
                for m in request.messages
            ],
            "stream": True,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
                "top_p": request.top_p,
            },
        }

        async with self.client.stream("POST", "/api/chat", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        yield content
                except json.JSONDecodeError:
                    continue

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
