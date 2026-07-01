"""Session memory — short-term context within a single session."""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING, Any

from terminal_ai_co_agent.logging.logger import get_logger
from terminal_ai_co_agent.memory.types import MemoryEntry, MemoryQuery, MemoryType

if TYPE_CHECKING:
    from terminal_ai_co_agent.memory.store import MemoryStore

logger = get_logger(__name__)


class SessionMemory:
    """Manages session-scoped memory.

    Stores:
    - Conversation history summaries
    - Active task context
    - Intermediate results
    - User feedback during session
    - Current focus/filters
    """

    def __init__(self, store: "MemoryStore", session_id: str | None = None) -> None:
        self.store = store
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self._conversation_turns: list[dict[str, str]] = []
        self._active_task: dict[str, Any] = {}
        self._context_focus: list[str] = []

    # ── Conversation ────────────────────────────────────────────

    async def add_turn(self, role: str, content: str) -> None:
        """Add a conversation turn."""
        self._conversation_turns.append({
            "role": role,
            "content": content,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        })

        # Persist summary every 5 turns
        if len(self._conversation_turns) % 5 == 0:
            await self._persist_summary()

    async def get_conversation(
        self,
        last_n: int | None = None,
    ) -> list[dict[str, str]]:
        """Get conversation history."""
        if last_n:
            return self._conversation_turns[-last_n:]
        return list(self._conversation_turns)

    async def get_conversation_summary(self) -> str:
        """Get a compressed summary of the conversation."""
        entries = await self.store.search(
            MemoryQuery(
                query=self.session_id,
                type=MemoryType.SESSION,
                limit=5,
            )
        )
        if entries:
            return entries[0].content
        return "No conversation history yet."

    async def _persist_summary(self) -> None:
        """Persist a summary of recent conversation."""
        recent = self._conversation_turns[-10:]
        summary = "\n".join(
            f"[{t['role']}] {t['content'][:200]}"
            for t in recent
        )
        entry = MemoryEntry(
            id=f"session_{self.session_id}_conv",
            type=MemoryType.SESSION,
            content=summary,
            metadata={
                "session_id": self.session_id,
                "turns": len(self._conversation_turns),
            },
            importance=0.4,
        )
        await self.store.add(entry)

    # ── Active Task ─────────────────────────────────────────────

    async def set_active_task(self, task: dict[str, Any]) -> None:
        """Set the currently active task."""
        self._active_task = task
        entry = MemoryEntry(
            id=f"session_{self.session_id}_task",
            type=MemoryType.SESSION,
            content=str(task),
            metadata={
                "session_id": self.session_id,
                "task_type": task.get("type", "unknown"),
            },
            importance=0.7,
        )
        await self.store.add(entry)
        logger.debug("session.task_set", task_type=task.get("type"))

    async def get_active_task(self) -> dict[str, Any]:
        """Get the current active task."""
        return dict(self._active_task)

    async def clear_active_task(self) -> None:
        """Clear the active task."""
        self._active_task = {}
        logger.debug("session.task_cleared")

    # ── Intermediate Results ────────────────────────────────────

    async def store_result(self, key: str, value: Any) -> None:
        """Store an intermediate result."""
        entry = MemoryEntry(
            id=f"session_{self.session_id}_result_{key}",
            type=MemoryType.SESSION,
            content=str(value),
            metadata={
                "session_id": self.session_id,
                "result_key": key,
            },
            importance=0.5,
        )
        await self.store.add(entry)

    async def get_result(self, key: str) -> str | None:
        """Retrieve an intermediate result."""
        entries = await self.store.search(
            MemoryQuery(
                query=key,
                type=MemoryType.SESSION,
                limit=1,
            )
        )
        for entry in entries:
            if entry.metadata.get("result_key") == key:
                return entry.content
        return None

    # ── Context Focus ───────────────────────────────────────────

    def set_focus(self, files_or_dirs: list[str]) -> None:
        """Set the current context focus (files/directories of interest)."""
        self._context_focus = files_or_dirs
        logger.debug("session.focus_set", focus=files_or_dirs)

    def get_focus(self) -> list[str]:
        """Get current context focus."""
        return list(self._context_focus)

    def in_focus(self, file_path: str) -> bool:
        """Check if a file is in the current focus."""
        if not self._context_focus:
            return True  # No focus = everything is relevant
        return any(file_path.startswith(f) for f in self._context_focus)

    # ── Cleanup ─────────────────────────────────────────────────

    async def clear_session(self) -> None:
        """Clear all session data."""
        self._conversation_turns.clear()
        self._active_task.clear()
        self._context_focus.clear()
        await self.store.clear_type(MemoryType.SESSION)
        logger.info("session.cleared", session_id=self.session_id)

    async def get_session_stats(self) -> dict[str, int]:
        """Get session statistics."""
        return {
            "conversation_turns": len(self._conversation_turns),
            "focus_items": len(self._context_focus),
            "has_active_task": 1 if self._active_task else 0,
        }
