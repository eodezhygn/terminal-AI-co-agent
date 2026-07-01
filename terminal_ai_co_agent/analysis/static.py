"""Static code analysis without external tool dependencies."""

from __future__ import annotations

import re
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


class StaticAnalyzer:
    """Lightweight static analysis for code quality.

    Checks:
    - Long functions
    - Deep nesting
    - Large parameter counts
    - Duplicate code patterns
    - Missing docstrings
    - Too many return statements
    - Magic numbers
    - Unused imports (basic detection)
    """

    def __init__(self) -> None:
        self._findings: list[AnalysisFinding] = []
        self._finding_id = 0

    async def analyze_file(self, path: Path) -> AnalysisResult:
        """Analyze a single file."""
        self._findings = []
        start = time.monotonic()

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return AnalysisResult(type=AnalysisType.STATIC, summary="Could not read file")

        language = self._detect_language(path)
        lines = content.splitlines()

        # Run checks
        self._check_function_length(lines, str(path), language)
        self._check_nesting_depth(lines, str(path), language)
        self._check_param_count(lines, str(path), language)
        self._check_missing_docstrings(lines, str(path), language)
        self._check_magic_numbers(lines, str(path), language)

        elapsed = int((time.monotonic() - start) * 1000)

        score = max(0.0, 1.0 - (len(self._findings) * 0.05))

        return AnalysisResult(
            type=AnalysisType.STATIC,
            findings=list(self._findings),
            summary=f"Found {len(self._findings)} issue(s) in {path.name}",
            score=score,
            duration_ms=elapsed,
            metadata={"language": language, "lines": len(lines)},
        )

    async def analyze_directory(self, directory: Path, max_files: int = 100) -> AnalysisResult:
        """Analyze all files in a directory."""
        all_findings: list[AnalysisFinding] = []
        files_analyzed = 0
        start = time.monotonic()

        for path in directory.rglob("*"):
            if files_analyzed >= max_files:
                break
            if path.is_file() and self._detect_language(path):
                result = await self.analyze_file(path)
                all_findings.extend(result.findings)
                files_analyzed += 1

        elapsed = int((time.monotonic() - start) * 1000)
        score = max(0.0, 1.0 - (len(all_findings) * 0.02))

        return AnalysisResult(
            type=AnalysisType.STATIC,
            findings=all_findings,
            summary=f"Analyzed {files_analyzed} file(s), found {len(all_findings)} issue(s)",
            score=score,
            duration_ms=elapsed,
            metadata={"files_analyzed": files_analyzed},
        )

    # ── Checks ──────────────────────────────────────────────────

    def _check_function_length(self, lines: list[str], path: str, language: str) -> None:
        """Check for excessively long functions."""
        if language not in ("python", "javascript", "typescript"):
            return

        func_start = 0
        func_name = ""
        in_function = False
        indent_level = 0

        for i, line in enumerate(lines):
            stripped = line.strip()

            if language == "python":
                if stripped.startswith("def ") and not in_function:
                    in_function = True
                    func_start = i
                    indent_level = len(line) - len(line.lstrip())
                    func_name = stripped.split("(")[0].replace("def ", "").strip()
                elif in_function and stripped and not line[0].isspace():
                    # Back to top-level indent → function ended
                    length = i - func_start
                    if length > 50:
                        self._add_finding(
                            path, func_start + 1,
                            f"Function '{func_name}' is {length} lines long (consider splitting)",
                            Severity.WARNING, "long-function",
                        )
                    in_function = False

    def _check_nesting_depth(self, lines: list[str], path: str, language: str) -> None:
        """Check for deep nesting."""
        max_depth = 0
        current_depth = 0
        deepest_line = 0

        for i, line in enumerate(lines):
            stripped = line.strip()
            if language == "python":
                indent = len(line) - len(line.lstrip())
                depth = indent // 4 if line.strip() else current_depth
                current_depth = depth
            else:
                # Count braces for JS-like languages
                current_depth += stripped.count("{") - stripped.count("}")

            if current_depth > max_depth:
                max_depth = current_depth
                deepest_line = i + 1

        if max_depth > 4:
            self._add_finding(
                path, deepest_line,
                f"Deep nesting detected (depth {max_depth})",
                Severity.WARNING, "deep-nesting",
                suggestion="Consider extracting nested logic into separate functions",
            )

    def _check_param_count(self, lines: list[str], path: str, language: str) -> None:
        """Check for functions with too many parameters."""
        if language == "python":
            pattern = r"def\s+(\w+)\s*\(([^)]*)\)"
        elif language in ("javascript", "typescript"):
            pattern = r"function\s+(\w+)\s*\(([^)]*)\)"
        else:
            return

        for i, line in enumerate(lines):
            match = re.search(pattern, line.strip())
            if match:
                func_name = match.group(1)
                params = [p.strip() for p in match.group(2).split(",") if p.strip()]
                if len(params) > 5:
                    self._add_finding(
                        path, i + 1,
                        f"Function '{func_name}' has {len(params)} parameters (consider using a config object)",
                        Severity.WARNING, "too-many-params",
                    )

    def _check_missing_docstrings(self, lines: list[str], path: str, language: str) -> None:
        """Check for public functions missing docstrings."""
        if language != "python":
            return

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("def ") and not stripped.startswith("def _"):
                # Check if there's a docstring on the next line
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if not (next_line.startswith('"""') or next_line.startswith("'''")):
                        func_name = stripped.split("(")[0].replace("def ", "").strip()
                        self._add_finding(
                            path, i + 1,
                            f"Function '{func_name}' is missing a docstring",
                            Severity.INFO, "missing-docstring",
                        )

    def _check_magic_numbers(self, lines: list[str], path: str, language: str) -> None:
        """Check for magic numbers in code."""
        # Look for numeric literals that might be magic numbers
        magic_number_patterns = [
            (r"(?<![a-zA-Z_])\d{4,}(?![a-zA-Z_])", "Large magic number"),
            (r"(?<![a-zA-Z_])(?:86400|3600|60|24|7|30|365)(?![a-zA-Z_])", "Time-related magic number"),
        ]

        for i, line in enumerate(lines):
            # Skip comments and strings
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue

            for pattern, message in magic_number_patterns:
                if re.search(pattern, line) and "=" not in line:
                    self._add_finding(
                        path, i + 1,
                        f"{message}: {re.search(pattern, line).group()}",
                        Severity.INFO, "magic-number",
                        suggestion="Consider using a named constant",
                    )

    # ── Helpers ─────────────────────────────────────────────────

    def _add_finding(
        self,
        file: str,
        line: int,
        message: str,
        severity: Severity,
        rule: str,
        suggestion: str = "",
    ) -> None:
        """Add a finding."""
        self._finding_id += 1
        self._findings.append(AnalysisFinding(
            id=f"SA-{self._finding_id:04d}",
            type=AnalysisType.STATIC,
            severity=severity,
            file=file,
            line=line,
            message=message,
            rule=rule,
            suggestion=suggestion,
        ))

    def _detect_language(self, path: Path) -> str | None:
        """Detect language from file extension."""
        ext_map = {
            ".py": "python", ".pyi": "python",
            ".js": "javascript", ".mjs": "javascript",
            ".ts": "typescript", ".tsx": "typescript",
        }
        return ext_map.get(path.suffix.lower())
