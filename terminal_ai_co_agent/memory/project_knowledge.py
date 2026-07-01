"""Project knowledge management — persistent understanding of the codebase."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from terminal_ai_co_agent.logging.logger import get_logger
from terminal_ai_co_agent.memory.types import MemoryEntry, MemoryQuery, MemoryType

if TYPE_CHECKING:
    from terminal_ai_co_agent.memory.store import MemoryStore

logger = get_logger(__name__)


class ProjectKnowledge:
    """Manages the Co-Agent's persistent understanding of a project.

    Stores:
    - Architecture decisions
    - Code patterns and conventions
    - File purposes and relationships
    - Past changes and their outcomes
    - Developer preferences
    - Known issues and workarounds
    """

    def __init__(self, store: "MemoryStore", project_root: Path) -> None:
        self.store = store
        self.project_root = project_root
        self._project_hash = self._compute_project_hash()

    # ── Recording Knowledge ─────────────────────────────────────

    async def record_architecture(
        self,
        component: str,
        description: str,
        relationships: list[str] | None = None,
    ) -> str:
        """Record an architectural decision or component."""
        entry = MemoryEntry(
            id="",
            type=MemoryType.PROJECT_KNOWLEDGE,
            content=description,
            metadata={
                "category": "architecture",
                "component": component,
                "relationships": relationships or [],
                "project_hash": self._project_hash,
            },
            importance=0.8,
        )
        return await self.store.add(entry)

    async def record_convention(
        self,
        name: str,
        pattern: str,
        examples: str,
    ) -> str:
        """Record a coding convention or pattern."""
        entry = MemoryEntry(
            id="",
            type=MemoryType.PROJECT_KNOWLEDGE,
            content=f"Convention: {name}\nPattern: {pattern}\nExamples: {examples}",
            metadata={
                "category": "convention",
                "name": name,
                "project_hash": self._project_hash,
            },
            importance=0.6,
        )
        return await self.store.add(entry)

    async def record_file_purpose(
        self,
        file_path: str,
        purpose: str,
        key_exports: list[str] | None = None,
    ) -> str:
        """Record the purpose and role of a specific file."""
        entry = MemoryEntry(
            id="",
            type=MemoryType.PROJECT_KNOWLEDGE,
            content=f"File: {file_path}\nPurpose: {purpose}",
            metadata={
                "category": "file_purpose",
                "file_path": file_path,
                "key_exports": key_exports or [],
                "project_hash": self._project_hash,
            },
            importance=0.4,
        )
        return await self.store.add(entry)

    async def record_change_outcome(
        self,
        change_description: str,
        success: bool,
        lessons: str,
    ) -> str:
        """Record the outcome of a change for future reference."""
        entry = MemoryEntry(
            id="",
            type=MemoryType.PROJECT_KNOWLEDGE,
            content=f"Change: {change_description}\nSuccess: {success}\nLessons: {lessons}",
            metadata={
                "category": "change_outcome",
                "success": success,
                "project_hash": self._project_hash,
            },
            importance=0.5 if success else 0.9,  # Failures are more important to remember
        )
        return await self.store.add(entry)

    async def record_preference(
        self,
        key: str,
        value: str,
    ) -> str:
        """Record a developer preference."""
        entry = MemoryEntry(
            id="",
            type=MemoryType.PROJECT_KNOWLEDGE,
            content=f"Preference: {key} = {value}",
            metadata={
                "category": "preference",
                "key": key,
                "value": value,
                "project_hash": self._project_hash,
            },
            importance=0.3,
        )
        return await self.store.add(entry)

    # ── Querying Knowledge ──────────────────────────────────────

    async def get_architecture(self, component: str | None = None) -> list[MemoryEntry]:
        """Retrieve architecture knowledge, optionally for a specific component."""
        query = MemoryQuery(
            query=component or "architecture",
            type=MemoryType.PROJECT_KNOWLEDGE,
            limit=20,
            filters={"category": "architecture"},
        )
        results = await self.store.search(query)
        if component:
            results = [
                r for r in results
                if r.metadata.get("component") == component
            ]
        return results

    async def get_conventions(self) -> list[MemoryEntry]:
        """Retrieve all recorded conventions."""
        query = MemoryQuery(
            query="convention",
            type=MemoryType.PROJECT_KNOWLEDGE,
            limit=50,
            filters={"category": "convention"},
        )
        return await self.store.search(query)

    async def get_file_purpose(self, file_path: str) -> MemoryEntry | None:
        """Get the recorded purpose of a specific file."""
        query = MemoryQuery(
            query=file_path,
            type=MemoryType.PROJECT_KNOWLEDGE,
            limit=5,
            filters={"category": "file_purpose"},
        )
        results = await self.store.search(query)
        for r in results:
            if r.metadata.get("file_path") == file_path:
                return r
        return None

    async def get_past_changes(self, success_only: bool = False) -> list[MemoryEntry]:
        """Get past change outcomes, optionally filtered by success."""
        query = MemoryQuery(
            query="change",
            type=MemoryType.PROJECT_KNOWLEDGE,
            limit=30,
            filters={"category": "change_outcome"},
        )
        results = await self.store.search(query)
        if success_only:
            results = [r for r in results if r.metadata.get("success")]
        return results

    async def get_preferences(self) -> dict[str, str]:
        """Get all recorded preferences as a dict."""
        query = MemoryQuery(
            query="preference",
            type=MemoryType.PROJECT_KNOWLEDGE,
            limit=100,
            filters={"category": "preference"},
        )
        results = await self.store.search(query)
        return {r.metadata.get("key", ""): r.metadata.get("value", "") for r in results}

    async def search_knowledge(self, query_str: str, limit: int = 10) -> list[MemoryEntry]:
        """Search all project knowledge."""
        query = MemoryQuery(
            query=query_str,
            type=MemoryType.PROJECT_KNOWLEDGE,
            limit=limit,
        )
        return await self.store.search(query)

    # ── Maintenance ─────────────────────────────────────────────

    async def clear_project_knowledge(self) -> int:
        """Clear all project knowledge (e.g., when switching projects)."""
        return await self.store.clear_type(MemoryType.PROJECT_KNOWLEDGE)

    async def get_summary(self) -> str:
        """Get a summary of all project knowledge."""
        stats = await self.store.stats()
        entries = await self.store.list_by_type(MemoryType.PROJECT_KNOWLEDGE, limit=200)

        categories: dict[str, int] = {}
        for e in entries:
            cat = e.metadata.get("category", "unknown")
            categories[cat] = categories.get(cat, 0) + 1

        parts = [
            f"Project Knowledge Summary",
            f"Total entries: {stats.entries_by_type.get('project_knowledge', 0)}",
            f"Categories: {categories}",
            "",
            "Recent entries:",
        ]

        for e in entries[:10]:
            parts.append(f"  [{e.metadata.get('category', '?')}] {e.content[:120]}...")

        return "\n".join(parts)

    def _compute_project_hash(self) -> str:
        """Compute a hash of the project root for identity tracking."""
        return hashlib.sha256(str(self.project_root.resolve()).encode()).hexdigest()[:12]
