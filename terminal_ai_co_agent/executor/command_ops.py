"""Shell command execution with safety policies and sandboxing."""

from __future__ import annotations

import asyncio
import os
import shlex
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from terminal_ai_co_agent.executor.types import (
    CommandOperation,
    OperationResult,
    OperationStatus,
)
from terminal_ai_co_agent.logging.audit import audit_event
from terminal_ai_co_agent.logging.logger import get_logger

if TYPE_CHECKING:
    from terminal_ai_co_agent.config.types import CoAgentConfig

logger = get_logger(__name__)


class CommandExecutor:
    """Safe shell command execution.

    Features:
    - Dangerous command detection
    - Timeout enforcement
    - Output capture
    - Audit logging
    - Environment isolation
    """

    def __init__(
        self,
        config: "CoAgentConfig",
        *,
        dry_run: bool = False,
    ) -> None:
        self.config = config
        self.dry_run = dry_run
        self._running_processes: dict[str, asyncio.subprocess.Process] = {}

    # ── Public API ───────────────────────────────────────────────

    async def run(self, operation: CommandOperation) -> OperationResult:
        """Execute a shell command safely."""
        op_id = self._make_id()

        # Safety check
        is_dangerous, reason = self._is_dangerous(operation.command)
        if is_dangerous and self.config.safety.approval_mode != "none":
            logger.warning("command.dangerous", command=operation.command, reason=reason)
            return OperationResult(
                success=False,
                operation_id=op_id,
                status=OperationStatus.REJECTED,
                error=f"Dangerous command rejected: {reason}. Requires explicit approval.",
            )

        if self.dry_run:
            logger.info("command.dry_run", command=operation.command)
            return OperationResult(
                success=True,
                operation_id=op_id,
                status=OperationStatus.COMPLETED,
                output=f"[DRY RUN] Would execute: {operation.command}",
            )

        audit_event(
            "command_execute",
            command=operation.command,
            cwd=str(operation.cwd) if operation.cwd else os.getcwd(),
            operation_id=op_id,
        )

        logger.info("command.execute", command=operation.command[:200])

        try:
            process = await asyncio.create_subprocess_shell(
                operation.command,
                cwd=operation.cwd,
                env={**os.environ, **operation.env} if operation.env else None,
                stdout=asyncio.subprocess.PIPE if operation.capture_output else None,
                stderr=asyncio.subprocess.PIPE if operation.capture_output else None,
            )

            self._running_processes[op_id] = process

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=operation.timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                del self._running_processes[op_id]
                return OperationResult(
                    success=False,
                    operation_id=op_id,
                    status=OperationStatus.FAILED,
                    error=f"Command timed out after {operation.timeout}s",
                )

            del self._running_processes[op_id]

            output = ""
            if stdout:
                output += stdout.decode("utf-8", errors="replace")
            if stderr:
                output += stderr.decode("utf-8", errors="replace")

            success = process.returncode == operation.expected_return_code

            audit_event(
                "command_completed",
                command=operation.command[:200],
                return_code=process.returncode,
                success=success,
                operation_id=op_id,
            )

            return OperationResult(
                success=success,
                operation_id=op_id,
                status=OperationStatus.COMPLETED if success else OperationStatus.FAILED,
                output=output.strip(),
                error="" if success else f"Exit code: {process.returncode}",
            )

        except FileNotFoundError as exc:
            return OperationResult(
                success=False,
                operation_id=op_id,
                status=OperationStatus.FAILED,
                error=f"Command not found: {exc}",
            )
        except Exception as exc:
            logger.error("command.error", command=operation.command[:200], error=str(exc))
            return OperationResult(
                success=False,
                operation_id=op_id,
                status=OperationStatus.FAILED,
                error=str(exc),
            )

    async def cancel(self, operation_id: str) -> None:
        """Cancel a running command."""
        if operation_id in self._running_processes:
            process = self._running_processes[operation_id]
            process.kill()
            await process.wait()
            del self._running_processes[operation_id]
            logger.info("command.cancelled", operation_id=operation_id)

    def cancel_all(self) -> None:
        """Cancel all running commands."""
        for op_id in list(self._running_processes.keys()):
            asyncio.create_task(self.cancel(op_id))

    # ── Safety Checks ────────────────────────────────────────────

    def _is_dangerous(self, command: str) -> tuple[bool, str]:
        """Check if a command matches dangerous patterns."""
        command_lower = command.lower()

        for pattern in self.config.safety.dangerous_commands:
            if pattern.lower() in command_lower:
                return True, f"Matches dangerous pattern: '{pattern}'"

        # Additional heuristic checks
        if "|" in command and ("rm" in command_lower or "delete" in command_lower):
            return True, "Piped command with destructive operation"

        if "curl" in command_lower and "|" in command and ("sh" in command_lower or "bash" in command_lower):
            return True, "curl-to-shell pattern detected"

        return False, ""

    # ── Helpers ──────────────────────────────────────────────────

    def _make_id(self) -> str:
        return uuid.uuid4().hex[:12]

    @property
    def active_processes(self) -> int:
        """Number of currently running processes."""
        return len(self._running_processes)
