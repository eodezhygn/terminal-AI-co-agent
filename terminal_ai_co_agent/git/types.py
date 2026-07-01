"""Type definitions for the Git subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class GitOperation(str, Enum):
    """Types of Git operations."""

    STATUS = "status"
    DIFF = "diff"
    COMMIT = "commit"
    BRANCH = "branch"
    CHECKOUT = "checkout"
    MERGE = "merge"
    PULL = "pull"
    PUSH = "push"
    STASH = "stash"
    LOG = "log"
    ADD = "add"
    RESET = "reset"


@dataclass
class GitFileStatus:
    """Status of a single file in the working tree."""

    path: str
    status: str  # M, A, D, R, C, U, ?
    staged: bool = False
    old_path: str | None = None  # For renames


@dataclass
class GitDiff:
    """A diff between two states."""

    file_path: str
    old_path: str | None = None
    diff_text: str = ""
    lines_added: int = 0
    lines_removed: int = 0
    is_binary: bool = False


@dataclass
class GitCommit:
    """Information about a commit."""

    hash: str
    author: str
    date: str
    message: str
    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0


@dataclass
class GitBranch:
    """Information about a branch."""

    name: str
    is_current: bool = False
    is_remote: bool = False
    upstream: str | None = None
    ahead: int = 0
    behind: int = 0
    last_commit: str = ""


@dataclass
class GitStatus:
    """Complete status of a Git repository."""

    branch: str
    clean: bool
    staged: list[GitFileStatus] = field(default_factory=list)
    unstaged: list[GitFileStatus] = field(default_factory=list)
    untracked: list[str] = field(default_factory=list)
    ahead: int = 0
    behind: int = 0
    stash_count: int = 0
