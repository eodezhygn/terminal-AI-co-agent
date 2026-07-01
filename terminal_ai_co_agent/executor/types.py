"""Type definitions for the execution subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class OperationType(str, Enum):
    """Types of operations the executor can perform."""

    FILE_CREATE = "file_create"
    FILE_MODIFY = "file_modify"
    FILE_DELETE = "file_delete"
    FILE_RENAME = "file_rename"
    FILE_READ = "file_read"
    COMMAND_RUN = "command_run"
    GIT_COMMIT = "git_commit"
    GIT_BRANCH = "git_branch"
    GIT_MERGE = "git_merge"
    PATCH_APPLY = "patch_apply"


class OperationStatus(str, Enum):
    """Status of an executed operation."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class FileOperation:
    """Represents a file system operation."""

    type: OperationType
    path: Path
    content: str | None = None
    original_content: str | None = None
    encoding: str = "utf-8"
    permissions: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CommandOperation:
    """Represents a shell command execution."""

    command: str
    cwd: Path | None = None
    env: dict[str, str] = field(default_factory=dict)
    timeout: int = 300
    expected_return_code: int = 0
    capture_output: bool = True


@dataclass
class GitOperation:
    """Represents a git operation."""

    type: OperationType
    message: str | None = None
    branch: str | None = None
    files: list[Path] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OperationResult:
    """Result of an executed operation."""

    success: bool
    operation_id: str
    status: OperationStatus
    output: str = ""
    error: str = ""
    duration_ms: int = 0
    rollback_info: dict[str, Any] | None = None


@dataclass
class ExecutionBatch:
    """A batch of operations to execute together."""

    id: str
    operations: list[FileOperation | CommandOperation | GitOperation]
    status: OperationStatus = OperationStatus.PENDING
    results: list[OperationResult] = field(default_factory=list)
    created_at: str = ""
    rollback_batch_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
