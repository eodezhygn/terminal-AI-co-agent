"""Type definitions for the orchestration subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from terminal_ai_co_agent.ai.types import ModelRole


class PipelineStage(str, Enum):
    """Stages in the orchestration pipeline."""

    CONTEXT_COLLECTION = "context_collection"
    CONTEXT_COMPRESSION = "context_compression"
    PLANNING = "planning"
    VERIFICATION = "verification"
    EXECUTION = "execution"
    VALIDATION = "validation"


class TaskStatus(str, Enum):
    """Status of a task in the pipeline."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


@dataclass
class PipelineTask:
    """A single task in the orchestration pipeline."""

    id: str
    stage: PipelineStage
    status: TaskStatus = TaskStatus.PENDING
    model_role: ModelRole = ModelRole.DEFAULT
    input_data: dict[str, Any] = field(default_factory=dict)
    output_data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    attempt: int = 0
    max_attempts: int = 3
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineResult:
    """Result of a complete pipeline execution."""

    success: bool
    tasks: list[PipelineTask]
    final_output: dict[str, Any] = field(default_factory=dict)
    total_tokens: int = 0
    elapsed_ms: int = 0
    errors: list[str] = field(default_factory=list)
