"""Type definitions for the planner subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PlanStatus(str, Enum):
    """Status of a plan."""

    DRAFT = "draft"
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepType(str, Enum):
    """Types of plan steps."""

    FILE_CREATE = "file_create"
    FILE_MODIFY = "file_modify"
    FILE_DELETE = "file_delete"
    COMMAND = "command"
    GIT_OPERATION = "git_operation"
    PATCH = "patch"
    ANALYSIS = "analysis"
    REVIEW = "review"
    TEST = "test"
    DOCUMENTATION = "documentation"
    DEPLOYMENT = "deployment"


class RiskLevel(str, Enum):
    """Risk level of a plan step."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class PlanStep:
    """A single step in an execution plan."""

    id: str
    type: StepType
    description: str
    details: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)  # IDs of steps this depends on
    risk: RiskLevel = RiskLevel.LOW
    estimated_effort: str = "small"  # small, medium, large
    rollback_instructions: str = ""
    validation_criteria: str = ""
    alternatives: list[str] = field(default_factory=list)


@dataclass
class ExecutionPlan:
    """A complete execution plan with steps and metadata."""

    id: str
    task: str
    summary: str
    steps: list[PlanStep] = field(default_factory=list)
    status: PlanStatus = PlanStatus.DRAFT
    risk_assessment: dict[str, Any] = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)
    alternatives_considered: list[str] = field(default_factory=list)
    estimated_total_effort: str = "unknown"
    created_at: str = ""
    approved_at: str = ""
    completed_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PlanReview:
    """A review of a proposed plan."""

    plan_id: str
    approved: bool
    concerns: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    risk_acceptance: str = ""  # Reason for accepting risk if applicable
    reviewer: str = "ai_verification"
    reviewed_at: str = ""
