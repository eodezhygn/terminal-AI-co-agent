"""SQLite-backed memory store with optional vector search."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiosqlite

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


class SQLiteMemoryStore(MemoryStore):
    """SQLite-based memory store with full-text search.

    Suitable for local development and single-user scenarios.
    Supports project knowledge, session, and episodic memory types.
    """

    def __init__(self, config: "MemoryConfig") -> None:
        self.config = config
        self.db_path = Path(config.path) / "memory.db"
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Create database and tables if they don't exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self.db_path))
        self._db.row_factory = aiosqlite.Row

        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS memory_entries (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata_json TEXT DEFAULT '{}',
                embedding_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                access_count INTEGER DEFAULT 0,
                importance REAL DEFAULT 0.5
            )
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_memory_type
            ON memory_entries(type)
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_memory_importance
            ON memory_entries(importance DESC)
        """)

        await self._db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
            USING fts5(id, content, tokenize='porter unicode61')
        """)

        await self._db.commit()
        logger.info("memory.sqlite.initialized", path=str(self.db_path))

    async def add(self, entry: MemoryEntry) -> str:
        """Add a memory entry. Generates ID if not provided."""
        self._ensure_initialized()

        if not entry.id:
            entry.id = str(uuid.uuid4())
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        entry.created_at = entry.created_at or now
        entry.updated_at = now

        await self._db.execute(
            """
            INSERT OR REPLACE INTO memory_entries
                (id, type, content, metadata_json, embedding_json,
                 created_at, updated_at, access_count, importance)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.id,
                entry.type.value,
                entry.content,
                json.dumps(entry.metadata),
                json.dumps(entry.embedding) if entry.embedding else None,
                entry.created_at,
                entry.updated_at,
                entry.access_count,
                entry.importance,
            ),
        )

        # Update FTS index
        await self._db.execute(
            "INSERT OR REPLACE INTO memory_fts(id, content) VALUES (?, ?)",
            (entry.id, entry.content),
        )

        await self._db.commit()
        logger.debug("memory.added", id=entry.id, type=entry.type.value)
        return entry.id

    async def get(self, entry_id: str) -> MemoryEntry | None:
        """Retrieve a memory entry by ID."""
        self._ensure_initialized()

        async with self._db.execute(
            "SELECT * FROM memory_entries WHERE id = ?",
            (entry_id,),
        ) as cursor:
            row = await cursor.fetchone()

        if row is None:
            return None

        # Increment access count
        await self._db.execute(
            "UPDATE memory_entries SET access_count = access_count + 1 WHERE id = ?",
            (entry_id,),
        )
        await self._db.commit()

        return self._row_to_entry(row)

    async def update(self, entry_id: str, updates: dict[str, Any]) -> bool:
        """Update an existing memory entry."""
        self._ensure_initialized()

        existing = await self.get(entry_id)
        if existing is None:
            return False

        now = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        set_clauses = ["updated_at = ?"]
        params: list[Any] = [now]

        if "content" in updates:
            set_clauses.append("content = ?")
            params.append(updates["content"])
            # Update FTS
            await self._db.execute(
                "UPDATE memory_fts SET content = ? WHERE id = ?",
                (updates["content"], entry_id),
            )
        if "metadata" in updates:
            set_clauses.append("metadata_json = ?")
            params.append(json.dumps(updates["metadata"]))
        if "importance" in updates:
            set_clauses.append("importance = ?")
            params.append(updates["importance"])
        if "embedding" in updates:
            set_clauses.append("embedding_json = ?")
            params.append(json.dumps(updates["embedding"]))

        params.append(entry_id)

        await self._db.execute(
            f"UPDATE memory_entries SET {', '.join(set_clauses)} WHERE id = ?",
            params,
        )
        await self._db.commit()

        logger.debug("memory.updated", id=entry_id)
        return True

    async def delete(self, entry_id: str) -> bool:
        """Delete a memory entry."""
        self._ensure_initialized()

        async with self._db.execute(
            "DELETE FROM memory_entries WHERE id = ?",
            (entry_id,),
        ) as cursor:
            deleted = cursor.rowcount > 0

        if deleted:
            await self._db.execute("DELETE FROM memory_fts WHERE id = ?", (entry_id,))
            await self._db.commit()
            logger.debug("memory.deleted", id=entry_id)

        return deleted

    async def search(self, query: MemoryQuery) -> list[MemoryEntry]:
        """Search memory entries using FTS and optional type filter."""
        self._ensure_initialized()

        type_filter = ""
        params: list[Any] = []

        if query.type:
            type_filter = "AND m.type = ?"
            params.append(query.type.value)

        sql = f"""
            SELECT m.* FROM memory_entries m
            INNER JOIN memory_fts fts ON m.id = fts.id
            WHERE memory_fts MATCH ? {type_filter}
            AND m.importance >= ?
            ORDER BY m.importance DESC, m.access_count DESC
            LIMIT ?
        """

        params = [query.query, *params, query.min_importance, query.limit]

        async with self._db.execute(sql, params) as cursor:
            rows = await cursor.fetchall()

        return [self._row_to_entry(row) for row in rows]

    async def list_by_type(self, entry_type: MemoryType, limit: int = 100) -> list[MemoryEntry]:
        """List entries of a specific type."""
        self._ensure_initialized()

        async with self._db.execute(
            """
            SELECT * FROM memory_entries
            WHERE type = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (entry_type.value, limit),
        ) as cursor:
            rows = await cursor.fetchall()

        return [self._row_to_entry(row) for row in rows]

    async def clear_type(self, entry_type: MemoryType) -> int:
        """Clear all entries of a specific type."""
        self._ensure_initialized()

        async with self._db.execute(
            "SELECT id FROM memory_entries WHERE type = ?",
            (entry_type.value,),
        ) as cursor:
            ids = [row[0] for row in await cursor.fetchall()]

        if ids:
            placeholders = ",".join("?" for _ in ids)
            await self._db.execute(
                f"DELETE FROM memory_entries WHERE id IN ({placeholders})",
                ids,
            )
            await self._db.execute(
                f"DELETE FROM memory_fts WHERE id IN ({placeholders})",
                ids,
            )
            await self._db.commit()

        logger.info("memory.cleared_type", type=entry_type.value, count=len(ids))
        return len(ids)

    async def stats(self) -> MemoryStats:
        """Get memory store statistics."""
        self._ensure_initialized()

        async with self._db.execute(
            "SELECT COUNT(*) as total FROM memory_entries"
        ) as cursor:
            total = (await cursor.fetchone())[0]

        async with self._db.execute(
            "SELECT type, COUNT(*) as count FROM memory_entries GROUP BY type"
        ) as cursor:
            by_type = {row[0]: row[1] for row in await cursor.fetchall()}

        async with self._db.execute(
            "SELECT COALESCE(SUM(LENGTH(content)), 0) FROM memory_entries"
        ) as cursor:
            total_chars = (await cursor.fetchone())[0]

        async with self._db.execute(
            "SELECT MIN(created_at), MAX(created_at) FROM memory_entries"
        ) as cursor:
            row = await cursor.fetchone()
            oldest = row[0] or ""
            newest = row[1] or ""

        return MemoryStats(
            total_entries=total,
            entries_by_type=by_type,
            total_tokens=total_chars // 4,  # rough estimate
            storage_bytes=self.db_path.stat().st_size if self.db_path.exists() else 0,
            oldest_entry=oldest,
            newest_entry=newest,
        )

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None
            logger.debug("memory.sqlite.closed")

    def _ensure_initialized(self) -> None:
        """Ensure the store is initialized."""
        if self._db is None:
            raise RuntimeError("Memory store not initialized. Call initialize() first.")

    def _row_to_entry(self, row: Any) -> MemoryEntry:
        """Convert a database row to a MemoryEntry."""
        return MemoryEntry(
            id=row["id"],
            type=MemoryType(row["type"]),
            content=row["content"],
            metadata=json.loads(row["metadata_json"] or "{}"),
            embedding=json.loads(row["embedding_json"]) if row["embedding_json"] else None,
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
            access_count=row["access_count"] or 0,
            importance=row["importance"] or 0.5,
        )
