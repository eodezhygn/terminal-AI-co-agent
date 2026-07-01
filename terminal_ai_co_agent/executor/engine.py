"""Execution engine — coordinates all operation types safely."""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from terminal_ai_co_agent.executor.command_ops import CommandExecutor
from terminal_ai_co_agent.executor.file_ops import FileOperator
from terminal_ai_co_agent.executor.patch import PatchEngine
from terminal_ai_co_agent.executor.types import (
    CommandOperation,
    ExecutionBatch,
    FileOperation,
    GitOperation,
    OperationResult,
    OperationStatus,
    OperationType,
)
from terminal_ai_co_agent.logging.audit import audit_event
from terminal_ai_co_agent.logging.logger import get_logger

if TYPE_CHECKING:
    from terminal_ai_co_agent.config.types import CoAgentConfig

logger = get_logger(__name__)


class ExecutionEngine:
    """Central execution engine.

    Coordinates:
    - File operations (via FileOperator)
    - Command execution (via CommandExecutor)
    - Patch application (via PatchEngine)
    - Batch execution with atomic rollback

    All operations flow through safety checks before execution.
    """

    def __init__(
        self,
        config: "CoAgentConfig",
        *,
        dry_run: bool = False,
    ) -> None:
        self.config = config
        self.dry_run = dry_run or config.execution.dry_run

        # Sub-engines
        self.file_ops = FileOperator(config, dry_run=self.dry_run)
        self.command_ops = CommandExecutor(config, dry_run=self.dry_run)
        self.patch = PatchEngine(self.file_ops)

        self._batches: dict[str, ExecutionBatch] = {}
        self._rollback_history: list[dict[str, Any]] = []

    # ── Single Operations ────────────────────────────────────────

    async def execute_file_op(self, op: FileOperation) -> OperationResult:
        """Execute a single file operation."""
        logger.debug("execute.file", type=op.type.value, path=str(op.path))

        if op.type == OperationType.FILE_READ:
            return await self.file_ops.read(op.path, op.encoding)
        elif op.type in (OperationType.FILE_CREATE, OperationType.FILE_MODIFY):
            return await self.file_ops.write(op.path, op.content or "", op.encoding)
        elif op.type == OperationType.FILE_DELETE:
            return await self.file_ops.delete(op.path)
        elif op.type == OperationType.FILE_RENAME:
            dest = Path(op.metadata.get("destination", ""))
            return await self.file_ops.rename(op.path, dest)
        else:
            return OperationResult(
                success=False,
                operation_id="unknown",
                status=OperationStatus.FAILED,
                error=f"Unknown file operation: {op.type}",
            )

    async def execute_command(self, op: CommandOperation) -> OperationResult:
        """Execute a single command operation."""
        logger.debug("execute.command", command=op.command[:200])
        return await self.command_ops.run(op)

    async def execute_git_op(self, op: GitOperation) -> OperationResult:
        """Execute a git operation via command executor."""
        logger.debug("execute.git", type=op.type.value)

        if op.type == OperationType.GIT_COMMIT:
            cmd = f"git commit -m '{op.message or 'coagent commit'}'"
            if op.files:
                cmd += " -- " + " ".join(str(f) for f in op.files)
        elif op.type == OperationType.GIT_BRANCH:
            cmd = f"git checkout -b {op.branch or 'coagent/branch'}"
        elif op.type == OperationType.GIT_MERGE:
            cmd = f"git merge {op.branch or 'main'}"
        else:
            return OperationResult(
                success=False,
                operation_id="unknown",
                status=OperationStatus.FAILED,
                error=f"Unknown git operation: {op.type}",
            )

        command_op = CommandOperation(
            command=cmd,
            cwd=self.config.general.project_root,
            timeout=op.metadata.get("timeout", 120),
        )

        return await self.command_ops.run(command_op)

    # ── Batch Execution ──────────────────────────────────────────

    async def execute_batch(self, batch: ExecutionBatch) -> ExecutionBatch:
        """Execute a batch of operations.

        If any operation fails and auto_rollback is enabled,
        all completed operations in the batch are rolled back.
        """
        batch_id = batch.id or str(uuid.uuid4())[:8]
        batch.id = batch_id
        batch.status = OperationStatus.RUNNING
        batch.created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")

        logger.info("batch.start", batch_id=batch_id, operations=len(batch.operations))
        audit_event("batch_start", batch_id=batch_id, operations=len(batch.operations))

        self._batches[batch_id] = batch
        results: list[OperationResult] = []

        for op in batch.operations:
            if isinstance(op, FileOperation):
                result = await self.execute_file_op(op)
            elif isinstance(op, CommandOperation):
                result = await self.execute_command(op)
            elif isinstance(op, GitOperation):
                result = await self.execute_git_op(op)
            else:
                result = OperationResult(
                    success=False,
                    operation_id="unknown",
                    status=OperationStatus.FAILED,
                    error=f"Unknown operation type: {type(op)}",
                )

            results.append(result)

            # Stop on first failure if auto_rollback is on
            if not result.success and self.config.safety.auto_rollback:
                logger.warning("batch.rollback_triggered", batch_id=batch_id)
                await self._rollback_batch(batch, results)
                break

        batch.results = results
        all_success = all(r.success for r in results)
        batch.status = OperationStatus.COMPLETED if all_success else OperationStatus.FAILED

        logger.info(
            "batch.complete",
            batch_id=batch_id,
            success=all_success,
            completed=sum(1 for r in results if r.success),
            failed=sum(1 for r in results if not r.success),
        )

        audit_event(
            "batch_complete",
            batch_id=batch_id,
            success=all_success,
            results=len(results),
        )

        # Track rollback history
        self._rollback_history.append({
            "batch_id": batch_id,
            "timestamp": batch.created_at,
            "operations": len(batch.operations),
            "results": [(r.status.value, r.error) for r in results],
        })

        # Prune history
        max_history = self.config.safety.rollback_history
        if len(self._rollback_history) > max_history:
            self._rollback_history = self._rollback_history[-max_history:]

        return batch

    async def execute_plan(
        self,
        plan: dict[str, Any],
    ) -> ExecutionBatch:
        """Execute a structured plan.

        Expected plan format:
        {
            "steps": [
                {"type": "file_write", "path": "...", "content": "..."},
                {"type": "command", "command": "...", "cwd": "..."},
                {"type": "patch", "patch_text": "..."},
                ...
            ]
        }
        """
        operations: list[FileOperation | CommandOperation | GitOperation] = []

        for step in plan.get("steps", []):
            step_type = step["type"]

            if step_type == "file_write":
                operations.append(
                    FileOperation(
                        type=OperationType.FILE_MODIFY,
                        path=Path(step["path"]),
                        content=step.get("content", ""),
                    )
                )
            elif step_type == "file_create":
                operations.append(
                    FileOperation(
                        type=OperationType.FILE_CREATE,
                        path=Path(step["path"]),
                        content=step.get("content", ""),
                    )
                )
            elif step_type == "file_delete":
                operations.append(
                    FileOperation(
                        type=OperationType.FILE_DELETE,
                        path=Path(step["path"]),
                    )
                )
            elif step_type == "command":
                operations.append(
                    CommandOperation(
                        command=step["command"],
                        cwd=Path(step.get("cwd", ".")),
                        timeout=step.get("timeout", 300),
                    )
                )
            elif step_type == "patch":
                # Apply patch as a batch of file operations
                patch_results = await self.patch.apply_patch(step["patch_text"])
                # We don't add these individually; they're already executed
            elif step_type == "git_commit":
                operations.append(
                    GitOperation(
                        type=OperationType.GIT_COMMIT,
                        message=step.get("message", "coagent commit"),
                    )
                )

        batch = ExecutionBatch(
            id=str(uuid.uuid4())[:8],
            operations=operations,
        )

        return await self.execute_batch(batch)

    # ── Rollback ─────────────────────────────────────────────────

    async def _rollback_batch(
        self,
        batch: ExecutionBatch,
        results: list[OperationResult],
    ) -> None:
        """Rollback all completed operations in a batch."""
        logger.info("batch.rolling_back", batch_id=batch.id)

        for result in reversed(results):
            if result.success and result.rollback_info:
                await self.file_ops.rollback(result.operation_id)

        audit_event("batch_rollback", batch_id=batch.id)

    async def rollback_last(self) -> list[OperationResult]:
        """Rollback the most recent batch."""
        if not self._rollback_history:
            return [
                OperationResult(
                    success=False,
                    operation_id="rollback",
                    status=OperationStatus.FAILED,
                    error="No rollback history available",
                )
            ]

        last = self._rollback_history.pop()
        batch_id = last["batch_id"]

        logger.info("rollback.last", batch_id=batch_id)
        audit_event("rollback_triggered", batch_id=batch_id)

        return await self.file_ops.rollback_all()

    def get_rollback_history(self) -> list[dict[str, Any]]:
        """Get rollback history."""
        return list(self._rollback_history)

    # ── Cleanup ──────────────────────────────────────────────────

    def cancel_all(self) -> None:
        """Cancel all running operations."""
        self.command_ops.cancel_all()

    def cleanup(self) -> None:
        """Clean up resources."""
        self.cancel_all()
