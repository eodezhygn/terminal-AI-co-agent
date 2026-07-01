"""File operation safety policies."""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import TYPE_CHECKING, Any

from terminal_ai_co_agent.safety.types import (
    ApprovalLevel,
    PolicyAction,
    PolicyResult,
    RiskAssessment,
)

if TYPE_CHECKING:
    from terminal_ai_co_agent.config.types import SafetyConfig


class FileSafetyPolicy:
    """Safety policy for file system operations.

    Evaluates:
    - Whether a path is protected
    - File type sensitivity
    - Size of changes
    - Location within project
    """

    # File patterns considered sensitive
    SENSITIVE_PATTERNS = [
        "*.key",
        "*.pem",
        "*.p12",
        "*.pfx",
        "*.jks",
        "*.keystore",
        "secrets.*",
        "credentials.*",
        ".env",
        ".env.*",
        "*.env",
        "id_rsa*",
        "*.token",
        "*.secret",
        "private_key*",
    ]

    # Directories that need extra scrutiny
    SENSITIVE_DIRS = [
        ".git",
        ".ssh",
        ".gnupg",
        ".aws",
        ".config",
        "/etc",
        "/sys",
        "/proc",
        "/boot",
    ]

    def __init__(self, config: "SafetyConfig") -> None:
        self.config = config
        self.protected = config.protected_patterns

    def evaluate_read(self, path: Path) -> PolicyResult:
        """Evaluate a file read operation."""
        # Reading is generally safe
        if self._is_in_sensitive_dir(path):
            return PolicyResult(
                action=PolicyAction.ASK,
                reason=f"Reading from sensitive directory: {path}",
                policy_name="file_read_sensitive",
            )
        return PolicyResult(
            action=PolicyAction.ALLOW,
            reason="File read is safe",
            policy_name="file_read",
        )

    def evaluate_write(self, path: Path, content_size: int) -> PolicyResult:
        """Evaluate a file write operation."""
        # Protected files
        if self._is_protected(path):
            return PolicyResult(
                action=PolicyAction.DENY,
                reason=f"Path is protected: {path}. Override with explicit approval.",
                policy_name="file_write_protected",
            )

        # Sensitive files
        if self._is_sensitive_file(path):
            return PolicyResult(
                action=PolicyAction.ASK,
                reason=f"Writing to sensitive file: {path.name}",
                policy_name="file_write_sensitive",
                requires_justification=True,
            )

        # Large writes to existing files
        if path.exists():
            original_size = path.stat().st_size
            change_ratio = abs(content_size - original_size) / max(original_size, 1)
            if change_ratio > 0.75 and original_size > 1000:
                return PolicyResult(
                    action=PolicyAction.ASK,
                    reason=f"Large change ({change_ratio:.0%}) to {path.name}",
                    policy_name="file_write_large_change",
                )

        return PolicyResult(
            action=PolicyAction.ALLOW,
            reason="File write is safe",
            policy_name="file_write",
        )

    def evaluate_delete(self, path: Path) -> PolicyResult:
        """Evaluate a file delete operation."""
        if self._is_protected(path):
            return PolicyResult(
                action=PolicyAction.DENY,
                reason=f"Cannot delete protected path: {path}",
                policy_name="file_delete_protected",
            )

        if self._is_sensitive_file(path):
            return PolicyResult(
                action=PolicyAction.ASK,
                reason=f"Deleting sensitive file: {path.name}",
                policy_name="file_delete_sensitive",
                requires_justification=True,
            )

        if path.is_dir():
            return PolicyResult(
                action=PolicyAction.ASK,
                reason=f"Deleting directory: {path}",
                policy_name="file_delete_directory",
            )

        return PolicyResult(
            action=PolicyAction.ALLOW,
            reason="File delete is safe",
            policy_name="file_delete",
        )

    def evaluate_rename(self, source: Path, destination: Path) -> PolicyResult:
        """Evaluate a file rename/move operation."""
        if self._is_protected(source) or self._is_protected(destination):
            return PolicyResult(
                action=PolicyAction.DENY,
                reason=f"Protected path in rename: {source} → {destination}",
                policy_name="file_rename_protected",
            )

        return PolicyResult(
            action=PolicyAction.ALLOW,
            reason="Rename is safe",
            policy_name="file_rename",
        )

    def assess_risk(self, path: Path, operation: str) -> RiskAssessment:
        """Assess the risk of a file operation."""
        score = 0.0
        factors: list[str] = []
        blast_radius = "single_file"

        if self._is_protected(path):
            score = 1.0
            factors.append("Path is in protected list")

        if self._is_sensitive_file(path):
            score = max(score, 0.7)
            factors.append("File matches sensitive pattern")

        if self._is_in_sensitive_dir(path):
            score = max(score, 0.8)
            factors.append("Path is in sensitive directory")
            blast_radius = "system"

        if operation == "delete" and not path.exists():
            score = 0.0
            factors = ["File does not exist"]

        if score < 0.3:
            level = ApprovalLevel.NONE
        elif score < 0.5:
            level = ApprovalLevel.LOW
        elif score < 0.7:
            level = ApprovalLevel.MEDIUM
        elif score < 0.9:
            level = ApprovalLevel.HIGH
        else:
            level = ApprovalLevel.CRITICAL

        return RiskAssessment(
            level=level,
            score=score,
            factors=factors,
            mitigation="Create backup before operation" if score > 0.3 else "",
            rollback_possible=score < 0.8,
            blast_radius=blast_radius,
        )

    def _is_protected(self, path: Path) -> bool:
        """Check if path matches any protected pattern."""
        path_str = str(path)
        for pattern in self.protected:
            if fnmatch.fnmatch(path.name, pattern) or fnmatch.fnmatch(path_str, pattern):
                return True
        return False

    def _is_sensitive_file(self, path: Path) -> bool:
        """Check if file matches sensitive patterns."""
        for pattern in self.SENSITIVE_PATTERNS:
            if fnmatch.fnmatch(path.name, pattern):
                return True
        return False

    def _is_in_sensitive_dir(self, path: Path) -> bool:
        """Check if path is within a sensitive directory."""
        path_str = str(path.resolve())
        for sensitive in self.SENSITIVE_DIRS:
            if sensitive in path_str.split(str(Path("/"))):
                # Ensure it's a directory boundary match
                parts = Path(path_str).parts
                if sensitive.lstrip("/") in parts:
                    return True
        return False
