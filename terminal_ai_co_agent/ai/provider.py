"""Abstract base class for AI providers with shared functionality."""

from __future__ import annotations

import hashlib
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, AsyncIterator, ClassVar

from terminal_ai_co_agent.logging.logger import get_logger
from terminal_ai_co_agent.logging.audit import audit_event
from terminal_ai_co_agent.ai.types import (
    CompletionRequest,
    CompletionResponse,
    ModelInfo,
    UsageInfo,
)

if TYPE_CHECKING:
    from terminal_ai_co_agent.logging.types import LogLevel

logger = get_logger(__name__)


class BaseAIProvider(ABC):
    """Abstract base for all AI providers.

    Provides:
    - Retry logic
    - Health check templating
    - Audit logging
    - Response validation
    - Caching hooks
    """

    # Subclasses must define these
    provider_name: ClassVar[str]
    default_model: ClassVar[str]
    supports_streaming: ClassVar[bool] = True

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        timeout: float = 60.0,
        retry_attempts: int = 3,
        retry_delay: float = 1.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay

    # ── Abstract Interface ──────────────────────────────────────

    @property
    @abstractmethod
    def available_models(self) -> list[ModelInfo]:
        """Return models available from this provider."""
        ...

    @abstractmethod
    async def _complete_impl(
        self,
        request: CompletionRequest,
    ) -> CompletionResponse:
        """Provider-specific completion implementation."""
        ...

    @abstractmethod
    async def _stream_impl(
        self,
        request: CompletionRequest,
    ) -> AsyncIterator[str]:
        """Provider-specific streaming implementation."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check provider connectivity."""
        ...

    # ── Public API ───────────────────────────────────────────────

    async def complete(
        self,
        request: CompletionRequest,
    ) -> CompletionResponse:
        """Send a completion request with retry logic and auditing."""
        request_hash = self._hash_request(request)
        start_time = time.monotonic()

        logger.info(
            "ai.completion.start",
            provider=self.provider_name,
            model=request.model,
            messages_count=len(request.messages),
            request_hash=request_hash,
        )

        last_exception: Exception | None = None

        for attempt in range(self.retry_attempts + 1):
            try:
                response = await self._complete_impl(request)

                elapsed = time.monotonic() - start_time
                logger.info(
                    "ai.completion.success",
                    provider=self.provider_name,
                    model=response.model,
                    tokens=response.usage.total_tokens,
                    elapsed_ms=int(elapsed * 1000),
                    attempt=attempt,
                )

                audit_event(
                    event_type="ai_completion",
                    provider=self.provider_name,
                    model=response.model,
                    tokens=response.usage.total_tokens,
                    elapsed_ms=int(elapsed * 1000),
                    request_hash=request_hash,
                )

                return response

            except Exception as exc:
                last_exception = exc
                logger.warning(
                    "ai.completion.retry",
                    provider=self.provider_name,
                    attempt=attempt,
                    error=str(exc),
                )
                if attempt < self.retry_attempts:
                    await self._sleep(attempt)
                else:
                    break

        elapsed = time.monotonic() - start_time
        logger.error(
            "ai.completion.failure",
            provider=self.provider_name,
            model=request.model,
            elapsed_ms=int(elapsed * 1000),
            error=str(last_exception),
        )
        raise AIProviderError(
            f"{self.provider_name} completion failed after "
            f"{self.retry_attempts + 1} attempts: {last_exception}"
        ) from last_exception

    async def stream_complete(
        self,
        request: CompletionRequest,
    ) -> AsyncIterator[str]:
        """Stream completion with minimal overhead."""
        if not self.supports_streaming:
            # Fallback: complete and yield at once
            response = await self.complete(request)
            yield response.content
            return

        async for token in self._stream_impl(request):
            yield token

    async def verify_capability(self) -> dict[str, Any]:
        """Check provider capabilities."""
        try:
            healthy = await self.health_check()
            models = self.available_models
            return {
                "provider": self.provider_name,
                "healthy": healthy,
                "models": [m.name for m in models],
                "streaming": self.supports_streaming,
            }
        except Exception as exc:
            return {
                "provider": self.provider_name,
                "healthy": False,
                "error": str(exc),
            }

    # ── Helpers ──────────────────────────────────────────────────

    def _hash_request(self, request: CompletionRequest) -> str:
        """Create a deterministic hash of a request for caching/auditing."""
        content = "".join(m.content for m in request.messages)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    async def _sleep(self, attempt: int) -> None:
        """Exponential backoff sleep."""
        import asyncio

        delay = self.retry_delay * (2**attempt)
        await asyncio.sleep(delay)

    def _validate_response(self, response: CompletionResponse) -> None:
        """Basic response validation."""
        if not response.content and response.finish_reason != "stop":
            raise AIProviderError(
                f"Empty response from {self.provider_name}: "
                f"finish_reason={response.finish_reason}"
            )


class AIProviderError(Exception):
    """Base exception for AI provider errors."""

    def __init__(self, message: str, *, provider: str | None = None):
        self.provider = provider
        super().__init__(message)
