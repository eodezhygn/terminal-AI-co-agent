"""Type definitions for the context subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ContextSource(str, Enum):
    """Source types for context extraction."""

    SOURCE_CODE = "source_code"
    DOCUMENTATION = "documentation"
    CONFIGURATION = "configuration"
    DEPENDENCIES = "dependencies"
    GIT_HISTORY = "git_history"
    TESTS = "tests"
    REQUIREMENTS = "requirements"
    PROJECT_STRUCTURE = "project_structure"


@dataclass
class FileContext:
    """Extracted context from a single file."""

    path: Path
    source: ContextSource
    language: str = ""
    summary: str = ""
    symbols: list[SymbolInfo] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_content: str = ""


@dataclass
class SymbolInfo:
    """Information about a code symbol."""

    name: str
    kind: str  # function, class, method, variable, module
    line: int
    signature: str = ""
    docstring: str = ""
    visibility: str = "public"
    children: list[SymbolInfo] = field(default_factory=list)


@dataclass
class ProjectContext:
    """Aggregated context for an entire project."""

    project_root: Path
    name: str = ""
    description: str = ""
    language: str = ""
    framework: str = ""
    files: list[FileContext] = field(default_factory=list)
    structure: dict[str, Any] = field(default_factory=dict)
    dependencies: dict[str, str] = field(default_factory=dict)
    dev_dependencies: dict[str, str] = field(default_factory=dict)
    entry_points: list[str] = field(default_factory=list)
    conventions: dict[str, Any] = field(default_factory=dict)
    git_info: dict[str, Any] = field(default_factory=dict)
    test_framework: str = ""
    build_system: str = ""


@dataclass
class ContextPackage:
    """Compressed, structured context ready for model consumption."""

    project_summary: str
    relevant_files: list[FileContext]
    structure_overview: str
    dependency_graph: dict[str, list[str]]
    conventions: dict[str, Any]
    recent_changes: str
    total_tokens: int
    compression_ratio: float
    metadata: dict[str, Any] = field(default_factory=dict)
