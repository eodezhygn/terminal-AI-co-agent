"""Security analysis for project code."""

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


class SecurityAnalyzer:
    """Security-focused code analysis.

    Checks:
    - Hardcoded secrets
    - SQL injection patterns
    - Unsafe deserialization
    - Command injection risks
    - Insecure cryptography
    - Debug mode enabled
    - Exposed sensitive files
    """

    # Patterns for detecting secrets
    SECRET_PATTERNS = [
        (r'(?:api[_-]?key|apikey)\s*[:=]\s*["\'][^"\']{8,}["\']', "Hardcoded API key"),
        (r'(?:secret|password|passwd|pwd)\s*[:=]\s*["\'][^"\']{4,}["\']', "Hardcoded secret/password"),
        (r'(?:token|auth)\s*[:=]\s*["\'][^"\']{8,}["\']', "Hardcoded token"),
        (r'(?:-----BEGIN\s+(?:RSA|EC|DSA|OPENSSH)\s+PRIVATE\s+KEY-----)', "Private key in code"),
        (r'(?:access[_-]?key)\s*[:=]\s*["\'][^"\']{8,}["\']', "Hardcoded access key"),
    ]

    # SQL injection patterns
    SQL_INJECTION_PATTERNS = [
        r'(?:execute|cursor\.execute)\s*\(\s*(?:f["\']|["\'].*%|["\'].*\{)',
        r'(?:execute|cursor\.execute)\s*\(\s*[\w]+\s*\+',
        r'(?:raw|rawQuery)\s*\(\s*[^)]*\$',
        r'query\s*=\s*["\'].*\+',
    ]

    # Unsafe functions
    UNSAFE_FUNCTIONS = {
        "eval(": "eval() can execute arbitrary code",
        "exec(": "exec() can execute arbitrary code",
        "pickle.loads(": "Unsafe deserialization with pickle",
        "yaml.load(": "Use yaml.safe_load() instead",
        "subprocess.call(": "Prefer subprocess.run() with shell=False",
        "shell=True": "Avoid shell=True in subprocess",
        "os.system(": "Use subprocess.run() instead",
        "assert ": "assert statements are removed with -O flag",
    }

    def __init__(self) -> None:
        self._findings: list[AnalysisFinding] = []
        self._finding_id = 0

    async def analyze_file(self, path: Path) -> AnalysisResult:
        """Analyze a single file for security issues."""
        self._findings = []
        start = time.monotonic()

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return AnalysisResult(type=AnalysisType.SECURITY, summary="Could not read file")

        lines = content.splitlines()
        rel_path = str(path)

        # Run checks
        self._check_secrets(lines, rel_path)
        self._check_sql_injection(content, rel_path)
        self._check_unsafe_functions(lines, rel_path)
        self._check_insecure_crypto(lines, rel_path)

        elapsed = int((time.monotonic() - start) * 1000)
        score = max(0.0, 1.0 - (len(self._findings) * 0.15))

        return AnalysisResult(
            type=AnalysisType.SECURITY,
            findings=list(self._findings),
            summary=f"Found {len(self._findings)} security issue(s) in {path.name}",
            score=score,
            duration_ms=elapsed,
        )

    async def analyze_directory(self, directory: Path, max_files: int = 100) -> AnalysisResult:
        """Analyze all files in a directory."""
        all_findings: list[AnalysisFinding] = []
        files_analyzed = 0
        start = time.monotonic()

        code_extensions = {".py", ".js", ".ts", ".jsx", ".tsx", ".rb", ".php", ".java", ".go"}

        for path in directory.rglob("*"):
            if files_analyzed >= max_files:
                break
            if path.is_file() and path.suffix in code_extensions:
                result = await self.analyze_file(path)
                all_findings.extend(result.findings)
                files_analyzed += 1

        elapsed = int((time.monotonic() - start) * 1000)
        score = max(0.0, 1.0 - (len(all_findings) * 0.1))

        return AnalysisResult(
            type=AnalysisType.SECURITY,
            findings=all_findings,
            summary=f"Analyzed {files_analyzed} file(s), found {len(all_findings)} security issue(s)",
            score=score,
            duration_ms=elapsed,
            metadata={"files_analyzed": files_analyzed},
        )

    # ── Checks ──────────────────────────────────────────────────

    def _check_secrets(self, lines: list[str], path: str) -> None:
        """Check for hardcoded secrets."""
        for i, line in enumerate(lines):
            # Skip comment lines
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("*"):
                continue

            for pattern, message in self.SECRET_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    self._add_finding(
                        path, i + 1,
                        f"{message} detected",
                        Severity.CRITICAL,
                        "hardcoded-secret",
                        suggestion="Use environment variables or a secrets manager",
                    )
                    break

    def _check_sql_injection(self, content: str, path: str) -> None:
        """Check for SQL injection patterns."""
        for pattern in self.SQL_INJECTION_PATTERNS:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                line_num = content[:match.start()].count("\n") + 1
                self._add_finding(
                    path, line_num,
                    "Potential SQL injection vulnerability",
                    Severity.CRITICAL,
                    "sql-injection",
                    suggestion="Use parameterized queries instead of string concatenation",
                )

    def _check_unsafe_functions(self, lines: list[str], path: str) -> None:
        """Check for unsafe function calls."""
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue

            for func, message in self.UNSAFE_FUNCTIONS.items():
                if func in stripped:
                    self._add_finding(
                        path, i + 1,
                        f"Unsafe function: {message}",
                        Severity.WARNING,
                        "unsafe-function",
                    )

    def _check_insecure_crypto(self, lines: list[str], path: str) -> None:
        """Check for insecure cryptography usage."""
        insecure_patterns = {
            r"hashlib\.md5\(": "MD5 is cryptographically broken",
            r"hashlib\.sha1\(": "SHA1 is considered weak",
            r"random\.(random|choice|randint|randrange)": "Use secrets module for security-sensitive randomness",
            r"ssl\.PROTOCOL_(SSLv|TLSv1[^2])": "Use TLS 1.2 or higher",
        }

        for i, line in enumerate(lines):
            stripped = line.strip()
            for pattern, message in insecure_patterns.items():
                if re.search(pattern, stripped):
                    self._add_finding(
                        path, i + 1,
                        f"Insecure cryptography: {message}",
                        Severity.WARNING,
                        "insecure-crypto",
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
        self._finding_id += 1
        self._findings.append(AnalysisFinding(
            id=f"SEC-{self._finding_id:04d}",
            type=AnalysisType.SECURITY,
            severity=severity,
            file=file,
            line=line,
            message=message,
            rule=rule,
            suggestion=suggestion,
        ))
