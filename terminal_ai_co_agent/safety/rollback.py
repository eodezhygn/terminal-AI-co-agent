"""Rollback management for safe recovery from failed operations."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from terminal_ai_co_agent.logging.audit import audit_event
from terminal_ai_co_agent.logging.logger import get_logger

if TYPE_CHECKING:
    from terminal_ai_co_agent.config.types import SafetyConfig
    from terminal_ai_co_agent.executor.file_ops import FileOperator

logger = get_logger(__name__)


class RollbackManager:
    """Manages rollback history and recovery operations.

    Tracks:
    - File modifications
    - Command executions that changed state
    - Batch operations
    - Checkpoint creation
    """

    def __init__(
        self,
        config: "SafetyConfig",
        file_operator: "FileOperator | None" = None,
    ) -> None:
        self.config = config
        self.file_ops = file_operator
        self._history: list[dict[str, Any]] = []
        self._checkpoints: dict[str, dict[str, Any]] = {}
        self._max_history = config.rollback_history
        self._history_file: Path | None = None

    # ── History Tracking ────────────────────────────────────────

    def record_operation(
        self,
        operation_id: str,
        operation_type: str,
        target: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Record an operation for potential rollback."""
        entry = {
            "operation_id": operation_id,
            "type": operation_type,
            "target": target,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "details": details or {},
        }

        self._history.append(entry)

        # Prune old history
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        logger.debug("rollback.recorded", operation_id=operation_id, type=operation_type)

        # Persist if enabled
        if self._history_file:
            self._persist_history()

    def record_batch(
        self,
        batch_id: str,
        operations: list[dict[str, Any]],
    ) -> None:
        """Record a batch of operations together."""
        entry = {
            "batch_id": batch_id,
            "type": "batch",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "operations": operations,
        }
        self._history.append(entry)
        logger.debug("rollback.batch_recorded", batch_id=batch_id)

    # ── Checkpoints ─────────────────────────────────────────────

    def create_checkpoint(self, name: str) -> str:
        """Create a named checkpoint for rollback."""
        checkpoint_id = f"{name}-{int(time.time())}"
        self._checkpoints[checkpoint_id] = {
            "name": name,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "history_index": len(self._history),
        }

        logger.info("rollback.checkpoint_created", checkpoint_id=checkpoint_id, name=name)
        audit_event("checkpoint_created", checkpoint_id=checkpoint_id, name=name)

        return checkpoint_id

    async def rollback_to_checkpoint(self, checkpoint_id: str) -> bool:
        """Rollback to a named checkpoint if FileOperator is available."""
        if checkpoint_id not in self._checkpoints:
            logger.error("rollback.checkpoint_not_found", checkpoint_id=checkpoint_id)
            return False

        if self.file_ops is None:
            logger.error("rollback.no_file_operator")
            return False

        checkpoint = self._checkpoints[checkpoint_id]
        history_index = checkpoint["history_index"]

        logger.info(
            "rollback.to_checkpoint",
            checkpoint_id=checkpoint_id,
            name=checkpoint["name"],
        )
        audit_event("rollback_to_checkpoint", checkpoint_id=checkpoint_id)

        # Rollback operations since checkpoint (in reverse)
        operations_to_rollback = self._history[history_index:]
        success_count = 0

        for entry in reversed(operations_to_rollback):
            op_id = entry.get("operation_id", "")
            if op_id:
                try:
                    result = await self.file_ops.rollback(op_id)
                    if result.success:
                        success_count += 1
                except Exception as exc:
                    logger.warning("rollback.operation_failed", operation_id=op_id, error=str(exc))

        logger.info("rollback.complete", rolled_back=success_count, total=len(operations_to_rollback))
        return True

    # ── History Access ──────────────────────────────────────────

    def get_recent_operations(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get most recent operations."""
        return self._history[-limit:]

    def get_operations_by_type(self, operation_type: str) -> list[dict[str, Any]]:
        """Get operations filtered by type."""
        return [e for e in self._history if e.get("type") == operation_type]

    def clear_history(self) -> None:
        """Clear all rollback history."""
        self._history.clear()
        self._checkpoints.clear()
        logger.info("rollback.history_cleared")

    # ── Persistence ─────────────────────────────────────────────

    def set_history_file(self, path: Path) -> None:
        """Set file for persisting rollback history."""
        self._history_file = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def _persist_history(self) -> None:
        """Write history to disk."""
        if not self._history_file:
            return
        try:
            with open(self._history_file, "w") as f:
                json.dump(self._history[-self._max_history:], f, indent=2)
        except Exception as exc:
            logger.warning("rollback.persist_error", error=str(exc))

    def load_history(self) -> None:
        """Load history from disk."""
        if not self._history_file or not self._history_file.exists():
            return
        try:
            with open(self._history_file) as f:
                self._history = json.load(f)
            logger.info("rollback.history_loaded", entries=len(self._history))
        except Exception as exc:
            logger.warning("rollback.load_error", error=str(exc))
