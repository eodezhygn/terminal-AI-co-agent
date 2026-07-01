"""Type definitions for the memory subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MemoryType(str, Enum):
    """Types of memory entries."""

    PROJECT_KNOWLEDGE = "project_knowledge"
    SESSION = "session"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"


@dataclass
class MemoryEntry:
    """A single entry in the memory store."""

    id: str
    type: MemoryType
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None
    created_at: str = ""
    updated_at: str = ""
    access_count: int = 0
    importance: float = 0.5  # 0.0 (trivial) to 1.0 (critical)


@dataclass
class MemoryQuery:
    """A query against the memory store."""

    query: str
    type: MemoryType | None = None
    limit: int = 10
    min_importance: float = 0.0
    use_semantic: bool = True
    filters: dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryStats:
    """Statistics about the memory store."""

    total_entries: int
    entries_by_type: dict[str, int]
    total_tokens: int
    storage_bytes: int
    oldest_entry: str
    newest_entry: str
