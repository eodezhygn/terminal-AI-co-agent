"""Type definitions for the safety subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ApprovalLevel(str, Enum):
    """Approval requirement levels."""

    NONE = "none"          # No approval needed (safe operations)
    LOW = "low"            # Minor changes, auto-approvable
    MEDIUM = "medium"      # Significant changes, recommend review
    HIGH = "high"          # Major changes, require explicit approval
    CRITICAL = "critical"  # Dangerous operations, require multi-step confirmation


class PolicyAction(str, Enum):
    """Actions a policy can take."""

    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


@dataclass
class PolicyResult:
    """Result of evaluating a safety policy."""

    action: PolicyAction
    reason: str
    policy_name: str = ""
    requires_justification: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ApprovalRequest:
    """A request for user approval."""

    id: str
    operation_type: str
    description: str
    risk_level: ApprovalLevel
    details: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    expires_at: str | None = None
    approved: bool | None = None
    approved_by: str | None = None


@dataclass
class RiskAssessment:
    """Assessment of operation risk."""

    level: ApprovalLevel
    score: float  # 0.0 (safe) to 1.0 (extremely dangerous)
    factors: list[str] = field(default_factory=list)
    mitigation: str = ""
    rollback_possible: bool = True
    blast_radius: str = ""  # "single_file", "module", "project", "system"
