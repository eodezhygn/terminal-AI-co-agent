"""Central safety guard — enforces all safety policies before execution."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from terminal_ai_co_agent.logging.audit import audit_event
from terminal_ai_co_agent.logging.logger import get_logger
from terminal_ai_co_agent.safety.policies.command import CommandSafetyPolicy
from terminal_ai_co_agent.safety.policies.file import FileSafetyPolicy
from terminal_ai_co_agent.safety.types import (
    ApprovalLevel,
    ApprovalRequest,
    PolicyAction,
    PolicyResult,
    RiskAssessment,
)

if TYPE_CHECKING:
    from terminal_ai_co_agent.config.types import SafetyConfig

logger = get_logger(__name__)


class SafetyGuard:
    """Central safety enforcement system.

    Evaluates all operations through configured policies before
    allowing execution. Manages the approval workflow for
    operations that require user confirmation.
    """

    def __init__(self, config: "SafetyConfig") -> None:
        self.config = config
        self.file_policy = FileSafetyPolicy(config)
        self.command_policy = CommandSafetyPolicy(config)
        self._pending_approvals: dict[str, ApprovalRequest] = {}
        self._denied_count: int = 0
        self._approved_count: int = 0

    # ── File Operation Checks ───────────────────────────────────

    def check_file_read(self, path: Path) -> PolicyResult:
        """Check if a file read is safe."""
        result = self.file_policy.evaluate_read(path)
        self._log_policy("file_read", str(path), result)
        return result

    def check_file_write(self, path: Path, content_size: int = 0) -> PolicyResult:
        """Check if a file write is safe."""
        result = self.file_policy.evaluate_write(path, content_size)
        self._log_policy("file_write", str(path), result)
        return result

    def check_file_delete(self, path: Path) -> PolicyResult:
        """Check if a file delete is safe."""
        result = self.file_policy.evaluate_delete(path)
        self._log_policy("file_delete", str(path), result)
        return result

    def check_file_rename(self, source: Path, destination: Path) -> PolicyResult:
        """Check if a file rename is safe."""
        result = self.file_policy.evaluate_rename(source, destination)
        self._log_policy("file_rename", f"{source} → {destination}", result)
        return result

    # ── Command Checks ──────────────────────────────────────────

    def check_command(self, command: str) -> PolicyResult:
        """Check if a shell command is safe to execute."""
        result = self.command_policy.evaluate(command)
        self._log_policy("command", command[:200], result)
        return result

    # ── Risk Assessment ─────────────────────────────────────────

    def assess_file_risk(self, path: Path, operation: str) -> RiskAssessment:
        """Assess risk for a file operation."""
        return self.file_policy.assess_risk(path, operation)

    def assess_command_risk(self, command: str) -> RiskAssessment:
        """Assess risk for a command."""
        return self.command_policy.assess_risk(command)

    # ── Approval Workflow ───────────────────────────────────────

    def request_approval(
        self,
        operation_type: str,
        description: str,
        risk_level: ApprovalLevel,
        details: dict[str, Any] | None = None,
    ) -> ApprovalRequest:
        """Create an approval request for a pending operation."""
        request = ApprovalRequest(
            id=str(uuid.uuid4())[:8],
            operation_type=operation_type,
            description=description,
            risk_level=risk_level,
            details=details or {},
        )

        self._pending_approvals[request.id] = request

        logger.info(
            "safety.approval_required",
            request_id=request.id,
            operation_type=operation_type,
            risk_level=risk_level.value,
            description=description[:200],
        )

        audit_event(
            "approval_requested",
            request_id=request.id,
            operation_type=operation_type,
            risk_level=risk_level.value,
        )

        return request

    def approve(self, request_id: str, approver: str = "user") -> bool:
        """Approve a pending operation."""
        if request_id not in self._pending_approvals:
            logger.warning("safety.approval_not_found", request_id=request_id)
            return False

        request = self._pending_approvals[request_id]
        request.approved = True
        request.approved_by = approver
        self._approved_count += 1

        logger.info("safety.approved", request_id=request_id, approver=approver)
        audit_event("approval_granted", request_id=request_id, approver=approver)

        del self._pending_approvals[request_id]
        return True

    def deny(self, request_id: str, reason: str = "") -> bool:
        """Deny a pending operation."""
        if request_id not in self._pending_approvals:
            return False

        request = self._pending_approvals[request_id]
        request.approved = False
        self._denied_count += 1

        logger.info("safety.denied", request_id=request_id, reason=reason)
        audit_event("approval_denied", request_id=request_id, reason=reason)

        del self._pending_approvals[request_id]
        return True

    def get_pending_approvals(self) -> list[ApprovalRequest]:
        """List all pending approval requests."""
        return list(self._pending_approvals.values())

    def has_pending_approvals(self) -> bool:
        """Check if there are pending approvals."""
        return len(self._pending_approvals) > 0

    # ── Should Ask? ─────────────────────────────────────────────

    def should_ask_user(self, result: PolicyResult) -> bool:
        """Determine if we should prompt the user based on config and result."""
        if self.config.approval_mode == "none":
            return False
        if self.config.approval_mode == "all":
            return result.action != PolicyAction.DENY
        if self.config.approval_mode == "dangerous":
            return result.action in (PolicyAction.ASK, PolicyAction.DENY)
        return result.action == PolicyAction.ASK

    def is_allowed(self, result: PolicyResult) -> bool:
        """Check if an operation is allowed to proceed."""
        if result.action == PolicyAction.DENY:
            return False
        if result.action == PolicyAction.ASK:
            return self.config.approval_mode == "none"
        return True

    # ── Statistics ──────────────────────────────────────────────

    @property
    def stats(self) -> dict[str, int]:
        """Get safety statistics."""
        return {
            "approved": self._approved_count,
            "denied": self._denied_count,
            "pending": len(self._pending_approvals),
        }

    # ── Helpers ─────────────────────────────────────────────────

    def _log_policy(self, policy_type: str, target: str, result: PolicyResult) -> None:
        """Log a policy evaluation."""
        logger.debug(
            f"safety.policy.{policy_type}",
            target=target,
            action=result.action.value,
            reason=result.reason,
        )
