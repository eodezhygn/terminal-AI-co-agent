"""File system operations with safety checks and rollback support."""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from terminal_ai_co_agent.executor.types import (
    FileOperation,
    OperationResult,
    OperationStatus,
    OperationType,
)
from terminal_ai_co_agent.logging.audit import audit_event
from terminal_ai_co_agent.logging.logger import get_logger

if TYPE_CHECKING:
    from terminal_ai_co_agent.config.types import CoAgentConfig

logger = get_logger(__name__)


class FileOperator:
    """Safe file system operations with rollback capability.

    Every modification is recorded for potential rollback.
    Protected files are never modified without explicit override.
    """

    def __init__(
        self,
        config: "CoAgentConfig",
        *,
        dry_run: bool = False,
    ) -> None:
        self.config = config
        self.dry_run = dry_run
        self._backup_dir: Path | None = None
        self._backups: dict[str, Path] = {}

    @property
    def backup_dir(self) -> Path:
        """Lazy-initialized backup directory."""
        if self._backup_dir is None:
            self._backup_dir = (
                Path(self.config.general.project_root) / ".coagent" / "backups"
            )
            self._backup_dir.mkdir(parents=True, exist_ok=True)
        return self._backup_dir

    # ── Public API ───────────────────────────────────────────────

    async def read(self, path: Path, encoding: str = "utf-8") -> OperationResult:
        """Read a file safely."""
        op_id = self._make_id()
        op = FileOperation(
            type=OperationType.FILE_READ,
            path=path,
            encoding=encoding,
        )

        logger.debug("file.read", path=str(path))
        audit_event("file_read", path=str(path))

        try:
            content = path.read_text(encoding=encoding)
            return OperationResult(
                success=True,
                operation_id=op_id,
                status=OperationStatus.COMPLETED,
                output=content,
            )
        except Exception as exc:
            return OperationResult(
                success=False,
                operation_id=op_id,
                status=OperationStatus.FAILED,
                error=str(exc),
            )

    async def write(
        self,
        path: Path,
        content: str,
        encoding: str = "utf-8",
        create_backup: bool = True,
    ) -> OperationResult:
        """Write content to a file with backup."""
        op_id = self._make_id()

        if not self._is_safe_path(path):
            return OperationResult(
                success=False,
                operation_id=op_id,
                status=OperationStatus.REJECTED,
                error=f"Path is protected: {path}",
            )

        original = None
        if path.exists() and create_backup:
            original = await self._create_backup(path)

        op = FileOperation(
            type=OperationType.FILE_MODIFY if path.exists() else OperationType.FILE_CREATE,
            path=path,
            content=content,
            original_content=original.read_text(encoding=encoding) if original else None,
            encoding=encoding,
        )

        if self.dry_run:
            logger.info("file.write.dry_run", path=str(path))
            return OperationResult(
                success=True,
                operation_id=op_id,
                status=OperationStatus.COMPLETED,
                output="[DRY RUN] File would be written",
            )

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding=encoding)
            if op.original_content:
                self._backups[op_id] = original  # type: ignore[assignment]

            logger.info("file.write", path=str(path), size=len(content))
            audit_event("file_written", path=str(path), size=len(content), operation_id=op_id)

            return OperationResult(
                success=True,
                operation_id=op_id,
                status=OperationStatus.COMPLETED,
                output=f"Written {len(content)} bytes to {path}",
                rollback_info={"backup_path": str(original)} if original else None,
            )
        except Exception as exc:
            logger.error("file.write.error", path=str(path), error=str(exc))
            return OperationResult(
                success=False,
                operation_id=op_id,
                status=OperationStatus.FAILED,
                error=str(exc),
            )

    async def delete(self, path: Path) -> OperationResult:
        """Delete a file with backup."""
        op_id = self._make_id()

        if not self._is_safe_path(path):
            return OperationResult(
                success=False,
                operation_id=op_id,
                status=OperationStatus.REJECTED,
                error=f"Path is protected: {path}",
            )

        if not path.exists():
            return OperationResult(
                success=False,
                operation_id=op_id,
                status=OperationStatus.FAILED,
                error=f"File does not exist: {path}",
            )

        backup = await self._create_backup(path)

        if self.dry_run:
            return OperationResult(
                success=True,
                operation_id=op_id,
                status=OperationStatus.COMPLETED,
                output="[DRY RUN] File would be deleted",
            )

        try:
            path.unlink()
            self._backups[op_id] = backup
            logger.info("file.delete", path=str(path))
            audit_event("file_deleted", path=str(path), operation_id=op_id)

            return OperationResult(
                success=True,
                operation_id=op_id,
                status=OperationStatus.COMPLETED,
                rollback_info={"backup_path": str(backup)},
            )
        except Exception as exc:
            return OperationResult(
                success=False,
                operation_id=op_id,
                status=OperationStatus.FAILED,
                error=str(exc),
            )

    async def rename(self, source: Path, destination: Path) -> OperationResult:
        """Rename/move a file with backup."""
        op_id = self._make_id()

        if not self._is_safe_path(source) or not self._is_safe_path(destination):
            return OperationResult(
                success=False,
                operation_id=op_id,
                status=OperationStatus.REJECTED,
                error=f"Path is protected: {source} or {destination}",
            )

        backup = await self._create_backup(source)

        if self.dry_run:
            return OperationResult(
                success=True,
                operation_id=op_id,
                status=OperationStatus.COMPLETED,
                output=f"[DRY RUN] Would rename {source} → {destination}",
            )

        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            self._backups[op_id] = backup
            logger.info("file.rename", source=str(source), destination=str(destination))
            audit_event("file_renamed", source=str(source), destination=str(destination))

            return OperationResult(
                success=True,
                operation_id=op_id,
                status=OperationStatus.COMPLETED,
                rollback_info={"backup_path": str(backup), "original_path": str(source)},
            )
        except Exception as exc:
            return OperationResult(
                success=False,
                operation_id=op_id,
                status=OperationStatus.FAILED,
                error=str(exc),
            )

    async def rollback(self, operation_id: str) -> OperationResult:
        """Rollback a previously completed operation."""
        if operation_id not in self._backups:
            return OperationResult(
                success=False,
                operation_id=operation_id,
                status=OperationStatus.FAILED,
                error=f"No backup found for operation: {operation_id}",
            )

        backup_path = self._backups[operation_id]

        try:
            # Restore from backup
            target = self._backup_target_from_path(backup_path)
            if backup_path.exists():
                shutil.move(str(backup_path), str(target))
            else:
                # File was created, so backup is the original (which didn't exist)
                if target.exists():
                    target.unlink()

            del self._backups[operation_id]
            logger.info("file.rollback", operation_id=operation_id, target=str(target))
            audit_event("file_rollback", operation_id=operation_id, target=str(target))

            return OperationResult(
                success=True,
                operation_id=operation_id,
                status=OperationStatus.ROLLED_BACK,
                output=f"Rolled back to {target}",
            )
        except Exception as exc:
            return OperationResult(
                success=False,
                operation_id=operation_id,
                status=OperationStatus.FAILED,
                error=str(exc),
            )

    async def rollback_all(self) -> list[OperationResult]:
        """Rollback all tracked operations in reverse order."""
        results = []
        for op_id in reversed(list(self._backups.keys())):
            result = await self.rollback(op_id)
            results.append(result)
        return results

    def list_backups(self) -> dict[str, Path]:
        """List all current backups."""
        return dict(self._backups)

    # ── Helpers ──────────────────────────────────────────────────

    def _is_safe_path(self, path: Path) -> bool:
        """Check if a path is safe to modify (not protected)."""
        import fnmatch

        path_str = str(path)
        for pattern in self.config.safety.protected_patterns:
            if fnmatch.fnmatch(path.name, pattern) or fnmatch.fnmatch(path_str, pattern):
                return False
        return True

    async def _create_backup(self, path: Path) -> Path:
        """Create a backup of a file before modification."""
        backup_path = self.backup_dir / f"{path.name}.{uuid.uuid4().hex[:8]}.bak"

        if path.exists():
            shutil.copy2(str(path), str(backup_path))
            logger.debug("backup.created", original=str(path), backup=str(backup_path))

        return backup_path

    def _backup_target_from_path(self, backup_path: Path) -> Path:
        """Extract the original target path from a backup path."""
        # Backup format: {name}.{uuid}.bak → original {name}
        name = backup_path.stem.rsplit(".", 1)[0]
        return Path(name)

    def _make_id(self) -> str:
        """Generate a unique operation ID."""
        return uuid.uuid4().hex[:12]
