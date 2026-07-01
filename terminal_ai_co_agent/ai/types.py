"""Type definitions for the AI subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Protocol, runtime_checkable


class ModelRole(str, Enum):
    """Roles a model can serve in the orchestration pipeline."""

    CONTEXT = "context"        # Small model for reading & summarizing
    REASONING = "reasoning"    # Larger model for planning & decisions
    VERIFICATION = "verification"  # Model for reviewing & validating
    DEFAULT = "default"        # Single-model fallback
    CUSTOM = "custom"          # User-defined role


class MessageRole(str, Enum):
    """Roles within a conversation."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class Message:
    """A single message in a conversation."""

    role: MessageRole
    content: str
    name: str | None = None


@dataclass
class CompletionRequest:
    """Request to an AI model for completion."""

    messages: list[Message]
    model: str
    temperature: float = 0.1
    max_tokens: int = 4096
    top_p: float = 1.0
    stop: list[str] | None = None
    stream: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompletionResponse:
    """Response from an AI model."""

    content: str
    model: str
    usage: UsageInfo
    finish_reason: str = "stop"
    raw: Any = None


@dataclass
class UsageInfo:
    """Token usage information."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class ModelInfo:
    """Information about an available model."""

    name: str
    provider: str
    context_window: int
    max_tokens: int
    roles: list[ModelRole] = field(default_factory=lambda: [ModelRole.DEFAULT])
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class AIProvider(Protocol):
    """Protocol defining the interface for all AI providers."""

    @property
    def provider_name(self) -> str:
        """Unique provider identifier."""
        ...

    @property
    def available_models(self) -> list[ModelInfo]:
        """List models available from this provider."""
        ...

    async def complete(
        self,
        request: CompletionRequest,
    ) -> CompletionResponse:
        """Send a completion request and return the full response."""
        ...

    async def stream_complete(
        self,
        request: CompletionRequest,
    ) -> AsyncIterator[str]:
        """Send a completion request and stream response tokens."""
        ...

    async def health_check(self) -> bool:
        """Check if the provider is reachable and functioning."""
        ...


@runtime_checkable
class ContextExtractor(Protocol):
    """Protocol for context extraction models."""

    async def extract(
        self,
        files: dict[str, str],
        instruction: str,
    ) -> dict[str, Any]:
        """Extract structured context from file contents."""
        ...


@runtime_checkable
class ReasoningEngine(Protocol):
    """Protocol for reasoning/planning models."""

    async def reason(
        self,
        context: dict[str, Any],
        task: str,
    ) -> dict[str, Any]:
        """Generate a plan based on structured context and a task."""
        ...
