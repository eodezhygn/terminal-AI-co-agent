"""Abstract memory store interface and factory."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from terminal_ai_co_agent.memory.types import (
    MemoryEntry,
    MemoryQuery,
    MemoryStats,
    MemoryType,
)

if TYPE_CHECKING:
    from terminal_ai_co_agent.config.types import MemoryConfig


class MemoryStore(ABC):
    """Abstract interface for memory backends.

    Implementations: FileMemoryStore, SQLiteMemoryStore, QdrantMemoryStore
    """

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the memory store (create tables, indices, etc.)."""
        ...

    @abstractmethod
    async def add(self, entry: MemoryEntry) -> str:
        """Add a memory entry. Returns the entry ID."""
        ...

    @abstractmethod
    async def get(self, entry_id: str) -> MemoryEntry | None:
        """Retrieve a memory entry by ID."""
        ...

    @abstractmethod
    async def update(self, entry_id: str, updates: dict[str, Any]) -> bool:
        """Update an existing memory entry."""
        ...

    @abstractmethod
    async def delete(self, entry_id: str) -> bool:
        """Delete a memory entry."""
        ...

    @abstractmethod
    async def search(self, query: MemoryQuery) -> list[MemoryEntry]:
        """Search memory entries."""
        ...

    @abstractmethod
    async def list_by_type(self, entry_type: MemoryType, limit: int = 100) -> list[MemoryEntry]:
        """List entries of a specific type."""
        ...

    @abstractmethod
    async def clear_type(self, entry_type: MemoryType) -> int:
        """Clear all entries of a specific type. Returns count deleted."""
        ...

    @abstractmethod
    async def stats(self) -> MemoryStats:
        """Get memory store statistics."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close the memory store and release resources."""
        ...


def create_memory_store(config: "MemoryConfig") -> MemoryStore:
    """Factory function to create the appropriate memory store backend.

    Args:
        config: Memory configuration specifying backend type.

    Returns:
        Configured MemoryStore instance.

    Raises:
        ValueError: If the backend type is unknown.
    """
    if config.backend == "sqlite":
        from terminal_ai_co_agent.memory.backends.sqlite import SQLiteMemoryStore
        return SQLiteMemoryStore(config)
    elif config.backend == "qdrant":
        from terminal_ai_co_agent.memory.backends.qdrant import QdrantMemoryStore
        return QdrantMemoryStore(config)
    elif config.backend == "file":
        from terminal_ai_co_agent.memory.backends.file import FileMemoryStore
        return FileMemoryStore(config)
    else:
        raise ValueError(f"Unknown memory backend: {config.backend}")
