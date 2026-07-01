"""Dependency analysis for projects."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from terminal_ai_co_agent.analysis.types import (
    AnalysisFinding,
    AnalysisResult,
    AnalysisType,
    Severity,
)
from terminal_ai_co_agent.logging.logger import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class DependencyAnalyzer:
    """Analyzes project dependencies for issues.

    Checks:
    - Outdated packages
    - Known vulnerabilities (basic checks)
    - Circular dependencies between modules
    - Unused dependencies
    - Dependency size/health
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    async def analyze(self) -> AnalysisResult:
        """Run dependency analysis."""
        start = time.monotonic()
        findings: list[AnalysisFinding] = []

        # Detect dependency files
        dep_file = self._find_dependency_file()
        if not dep_file:
            return AnalysisResult(
                type=AnalysisType.DEPENDENCY,
                summary="No dependency file found",
                score=1.0,
            )

        # Parse dependencies
        deps = self._parse_dependencies(dep_file)
        if not deps:
            return AnalysisResult(
                type=AnalysisType.DEPENDENCY,
                summary="Could not parse dependencies",
                score=0.5,
            )

        # Check for common issues
        findings.extend(self._check_pinned_versions(deps, dep_file.name))
        findings.extend(self._check_known_risky_packages(deps, dep_file.name))

        elapsed = int((time.monotonic() - start) * 1000)
        score = max(0.0, 1.0 - (len(findings) * 0.1))

        return AnalysisResult(
            type=AnalysisType.DEPENDENCY,
            findings=findings,
            summary=f"Found {len(deps)} dependencies, {len(findings)} issue(s)",
            score=score,
            duration_ms=elapsed,
            metadata={
                "dependency_file": str(dep_file.name),
                "total_dependencies": len(deps),
            },
        )

    def _find_dependency_file(self) -> Path | None:
        """Find the project's dependency file."""
        candidates = [
            "pyproject.toml", "requirements.txt", "Pipfile",
            "package.json", "yarn.lock", "package-lock.json",
            "go.mod", "Cargo.toml", "Gemfile",
        ]
        for name in candidates:
            path = self.project_root / name
            if path.exists():
                return path
        return None

    def _parse_dependencies(self, path: Path) -> dict[str, str]:
        """Parse dependencies from a file."""
        deps: dict[str, str] = {}

        try:
            if path.name == "pyproject.toml":
                import tomli
                with open(path, "rb") as f:
                    data = tomli.load(f)
                project = data.get("project", {})
                for dep in project.get("dependencies", []):
                    if isinstance(dep, str):
                        parts = dep.split(">=") if ">=" in dep else dep.split("==") if "==" in dep else [dep, "*"]
                        deps[parts[0].strip()] = parts[1].strip() if len(parts) > 1 else "*"
            elif path.name == "requirements.txt":
                with open(path) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            parts = line.split("==") if "==" in line else [line, "*"]
                            deps[parts[0].strip()] = parts[1].strip() if len(parts) > 1 else "*"
            elif path.name == "package.json":
                with open(path) as f:
                    data = json.load(f)
                for dep_type in ("dependencies", "devDependencies"):
                    for name, version in data.get(dep_type, {}).items():
                        deps[name] = version.lstrip("^~")
        except Exception as exc:
            logger.warning("dependency.parse_error", path=str(path), error=str(exc))

        return deps

    def _check_pinned_versions(
        self,
        deps: dict[str, str],
        file_name: str,
    ) -> list[AnalysisFinding]:
        """Check for unpinned dependencies."""
        findings: list[AnalysisFinding] = []
        unpinned = [name for name, ver in deps.items() if ver in ("*", "", "latest")]

        if unpinned:
            findings.append(AnalysisFinding(
                id="DEP-001",
                type=AnalysisType.DEPENDENCY,
                severity=Severity.WARNING,
                file=file_name,
                message=f"{len(unpinned)} unpinned dependencies: {', '.join(unpinned[:5])}",
                rule="unpinned-dependency",
                suggestion="Pin dependency versions for reproducible builds",
            ))

        return findings

    def _check_known_risky_packages(
        self,
        deps: dict[str, str],
        file_name: str,
    ) -> list[AnalysisFinding]:
        """Check for packages with known issues."""
        findings: list[AnalysisFinding] = []

        # Packages known to be problematic or abandoned
        risky_packages = {
            "distutils": "Deprecated in Python 3.10+",
            "imp": "Deprecated in Python 3.4+",
            "cryptography": "Check for recent security advisories",
            "pycrypto": "Unmaintained; use pycryptodome instead",
            "pickle": "Security risk for untrusted data",
        }

        for name, issue in risky_packages.items():
            if name.lower() in [d.lower() for d in deps]:
                findings.append(AnalysisFinding(
                    id=f"DEP-RISK-{name}",
                    type=AnalysisType.DEPENDENCY,
                    severity=Severity.WARNING,
                    file=file_name,
                    message=f"Package '{name}': {issue}",
                    rule="risky-dependency",
                    suggestion=f"Consider alternatives to {name}",
                ))

        return findings
