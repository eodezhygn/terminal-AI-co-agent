"""File-based memory store for simple persistence without databases."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from terminal_ai_co_agent.logging.logger import get_logger
from terminal_ai_co_agent.memory.store import MemoryStore
from terminal_ai_co_agent.memory.types import (
    MemoryEntry,
    MemoryQuery,
    MemoryStats,
    MemoryType,
)

if TYPE_CHECKING:
    from terminal_ai_co_agent.config.types import MemoryConfig

logger = get_logger(__name__)


class FileMemoryStore(MemoryStore):
    """File-based memory store using JSON files.

    Simplest backend. Suitable for minimal deployments.
    Each memory type gets its own JSON file.
    """

    def __init__(self, config: "MemoryConfig") -> None:
        self.config = config
        self.base_path = Path(config.path)
        self._entries: dict[str, MemoryEntry] = {}
        self._by_type: dict[MemoryType, list[str]] = {}

    async def initialize(self) -> None:
        """Load memory from disk."""
        self.base_path.mkdir(parents=True, exist_ok=True)

        for mem_type in MemoryType:
            file_path = self._type_file(mem_type)
            if file_path.exists():
                try:
                    with open(file_path) as f:
                        data = json.load(f)
                    for entry_data in data:
                        entry = MemoryEntry(**entry_data)
                        self._entries[entry.id] = entry
                        self._by_type.setdefault(entry.type, []).append(entry.id)
                except Exception as exc:
                    logger.warning("memory.file.load_error", path=str(file_path), error=str(exc))

        total = len(self._entries)
        logger.info("memory.file.initialized", path=str(self.base_path), entries=total)

    async def add(self, entry: MemoryEntry) -> str:
        """Add a memory entry."""
        if not entry.id:
            entry.id = str(uuid.uuid4())
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        entry.created_at = entry.created_at or now
        entry.updated_at = now

        self._entries[entry.id] = entry
        self._by_type.setdefault(entry.type, []).append(entry.id)

        await self._persist_type(entry.type)
        logger.debug("memory.file.added", id=entry.id)
        return entry.id

    async def get(self, entry_id: str) -> MemoryEntry | None:
        """Get an entry by ID."""
        entry = self._entries.get(entry_id)
        if entry:
            entry.access_count += 1
        return entry

    async def update(self, entry_id: str, updates: dict[str, Any]) -> bool:
        """Update an entry."""
        entry = self._entries.get(entry_id)
        if not entry:
            return False

        for key, value in updates.items():
            if hasattr(entry, key):
                setattr(entry, key, value)

        entry.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        await self._persist_type(entry.type)
        return True

    async def delete(self, entry_id: str) -> bool:
        """Delete an entry."""
        entry = self._entries.pop(entry_id, None)
        if entry:
            self._by_type.get(entry.type, []).remove(entry_id)
            await self._persist_type(entry.type)
            return True
        return False

    async def search(self, query: MemoryQuery) -> list[MemoryEntry]:
        """Search entries by keyword matching."""
        results: list[tuple[float, MemoryEntry]] = []
        query_lower = query.query.lower()
        keywords = query_lower.split()

        for entry in self._entries.values():
            if query.type and entry.type != query.type:
                continue
            if entry.importance < query.min_importance:
                continue

            content_lower = entry.content.lower()
            score = sum(
                1.0 for kw in keywords
                if kw in content_lower or kw in str(entry.metadata).lower()
            )

            if score > 0:
                results.append((score * entry.importance, entry))

        results.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in results[:query.limit]]

    async def list_by_type(self, entry_type: MemoryType, limit: int = 100) -> list[MemoryEntry]:
        """List entries by type."""
        ids = self._by_type.get(entry_type, [])
        entries = [self._entries[i] for i in ids[-limit:] if i in self._entries]
        return sorted(entries, key=lambda e: e.updated_at, reverse=True)

    async def clear_type(self, entry_type: MemoryType) -> int:
        """Clear all entries of a type."""
        ids = self._by_type.get(entry_type, [])
        count = len(ids)
        for i in ids:
            self._entries.pop(i, None)
        self._by_type[entry_type] = []

        # Persist empty
        file_path = self._type_file(entry_type)
        file_path.write_text("[]")
        return count

    async def stats(self) -> MemoryStats:
        """Get memory statistics."""
        by_type = {t.value: len(ids) for t, ids in self._by_type.items()}
        total_chars = sum(len(e.content) for e in self._entries.values())

        timestamps = [e.created_at for e in self._entries.values() if e.created_at]

        return MemoryStats(
            total_entries=len(self._entries),
            entries_by_type=by_type,
            total_tokens=total_chars // 4,
            storage_bytes=sum(
                f.stat().st_size for f in self.base_path.glob("*.json") if f.exists()
            ),
            oldest_entry=min(timestamps) if timestamps else "",
            newest_entry=max(timestamps) if timestamps else "",
        )

    async def close(self) -> None:
        """Persist all types and close."""
        for mem_type in self._by_type:
            await self._persist_type(mem_type)
        logger.debug("memory.file.closed")

    def _type_file(self, mem_type: MemoryType) -> Path:
        """Get the file path for a memory type."""
        return self.base_path / f"{mem_type.value}.json"

    async def _persist_type(self, mem_type: MemoryType) -> None:
        """Persist entries of a given type to disk."""
        ids = self._by_type.get(mem_type, [])
        entries_data = [
            {
                "id": self._entries[i].id,
                "type": self._entries[i].type.value,
                "content": self._entries[i].content,
                "metadata": self._entries[i].metadata,
                "embedding": self._entries[i].embedding,
                "created_at": self._entries[i].created_at,
                "updated_at": self._entries[i].updated_at,
                "access_count": self._entries[i].access_count,
                "importance": self._entries[i].importance,
            }
            for i in ids if i in self._entries
        ]

        file_path = self._type_file(mem_type)
        with open(file_path, "w") as f:
            json.dump(entries_data, f, indent=2)
