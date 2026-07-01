"""Type definitions for the analysis subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class AnalysisType(str, Enum):
    """Types of analysis that can be performed."""

    STATIC = "static"
    DEPENDENCY = "dependency"
    COMPLEXITY = "complexity"
    SECURITY = "security"
    PERFORMANCE = "performance"
    DUPLICATION = "duplication"
    STYLE = "style"
    COVERAGE = "coverage"


class Severity(str, Enum):
    """Severity levels for analysis findings."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AnalysisFinding:
    """A single finding from analysis."""

    id: str
    type: AnalysisType
    severity: Severity
    file: str
    line: int = 0
    column: int = 0
    message: str = ""
    rule: str = ""
    suggestion: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalysisResult:
    """Complete result of an analysis run."""

    type: AnalysisType
    findings: list[AnalysisFinding] = field(default_factory=list)
    summary: str = ""
    score: float = 0.0  # 0.0 (poor) to 1.0 (excellent)
    duration_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def error_count(self) -> int:
        """Count of error/critical findings."""
        return sum(1 for f in self.findings if f.severity in (Severity.ERROR, Severity.CRITICAL))

    @property
    def warning_count(self) -> int:
        """Count of warning findings."""
        return sum(1 for f in self.findings if f.severity == Severity.WARNING)
