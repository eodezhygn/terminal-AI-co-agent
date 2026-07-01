"""Command execution safety policies."""

from __future__ import annotations

import re
import shlex
from typing import TYPE_CHECKING, Any

from terminal_ai_co_agent.safety.types import (
    ApprovalLevel,
    PolicyAction,
    PolicyResult,
    RiskAssessment,
)

if TYPE_CHECKING:
    from terminal_ai_co_agent.config.types import SafetyConfig


class CommandSafetyPolicy:
    """Safety policy for shell command execution.

    Evaluates:
    - Dangerous command patterns
    - Network access
    - Privilege escalation
    - Destructive operations
    - Pipe chains
    """

    # Danger levels for pattern matching
    CRITICAL_PATTERNS = [
        r"rm\s+-rf\s+/",
        r"dd\s+if=",
        r">\s*/dev/sd",
        r"mkfs\.",
        r"format\s+[A-Z]:",
        r"shutdown",
        r"reboot",
        r"halt",
        r"poweroff",
    ]

    HIGH_RISK_PATTERNS = [
        r"rm\s+-rf",
        r"rm\s+-r\s",
        r"git\s+push\s+--force",
        r"git\s+push\s+-f",
        r"sudo\s+",
        r"chmod\s+777",
        r"chown\s+-R",
        r"DROP\s+TABLE",
        r"DELETE\s+FROM",
        r"TRUNCATE\s+TABLE",
        r"ALTER\s+TABLE.*DROP",
        r"docker\s+rm\s+-f",
        r"docker\s+system\s+prune",
        r"kubectl\s+delete",
        r"pip\s+uninstall",
        r"npm\s+uninstall",
    ]

    MEDIUM_RISK_PATTERNS = [
        r"curl.*\|\s*(ba)?sh",
        r"curl.*\|\s*bash",
        r"wget.*-O-.*\|",
        r"eval\s+",
        r"source\s+/dev/stdin",
        r"\.\s+/dev/stdin",
        r"chmod\s+",
        r"chown\s+",
        r"export\s+DISPLAY",
    ]

    def __init__(self, config: "SafetyConfig") -> None:
        self.config = config
        self.dangerous_patterns = config.dangerous_commands

    def evaluate(self, command: str) -> PolicyResult:
        """Evaluate a command for safety."""
        command_lower = command.lower()

        # Check critical patterns first
        for pattern in self.CRITICAL_PATTERNS:
            if re.search(pattern, command_lower):
                return PolicyResult(
                    action=PolicyAction.DENY,
                    reason=f"Command matches critical danger pattern: {pattern}",
                    policy_name="command_critical",
                    requires_justification=True,
                )

        # Check configured dangerous patterns
        for pattern in self.dangerous_patterns:
            if pattern.lower() in command_lower:
                return PolicyResult(
                    action=PolicyAction.ASK,
                    reason=f"Command matches dangerous pattern: '{pattern}'",
                    policy_name="command_dangerous_configured",
                    requires_justification=True,
                )

        # Check high risk patterns
        for pattern in self.HIGH_RISK_PATTERNS:
            if re.search(pattern, command_lower):
                return PolicyResult(
                    action=PolicyAction.ASK,
                    reason=f"Command matches high-risk pattern: {pattern}",
                    policy_name="command_high_risk",
                    requires_justification=True,
                )

        # Check medium risk patterns
        for pattern in self.MEDIUM_RISK_PATTERNS:
            if re.search(pattern, command_lower):
                return PolicyResult(
                    action=PolicyAction.ASK,
                    reason=f"Command requires review: {pattern}",
                    policy_name="command_medium_risk",
                )

        # Check for pipe chains (increased complexity = increased risk)
        pipe_count = command.count("|")
        if pipe_count > 3:
            return PolicyResult(
                action=PolicyAction.ASK,
                reason=f"Complex pipe chain ({pipe_count} pipes)",
                policy_name="command_complex_pipe",
            )

        # Network access heuristic
        if self._has_network_access(command):
            return PolicyResult(
                action=PolicyAction.ASK,
                reason="Command may access network resources",
                policy_name="command_network_access",
            )

        return PolicyResult(
            action=PolicyAction.ALLOW,
            reason="Command appears safe",
            policy_name="command_safe",
        )

    def assess_risk(self, command: str) -> RiskAssessment:
        """Assess the risk level of a command."""
        score = 0.0
        factors: list[str] = []
        blast_radius = "project"

        command_lower = command.lower()

        # Critical patterns → maximum risk
        for pattern in self.CRITICAL_PATTERNS:
            if re.search(pattern, command_lower):
                return RiskAssessment(
                    level=ApprovalLevel.CRITICAL,
                    score=1.0,
                    factors=["Matches critical system destruction pattern"],
                    mitigation="Do not execute. Manual review required.",
                    rollback_possible=False,
                    blast_radius="system",
                )

        # High risk → score 0.7-0.9
        for pattern in self.HIGH_RISK_PATTERNS:
            if re.search(pattern, command_lower):
                score = max(score, 0.8)
                factors.append(f"Matches high-risk pattern: {pattern}")
                blast_radius = "system" if "sudo" in command_lower else "project"

        # Medium risk → score 0.4-0.6
        for pattern in self.MEDIUM_RISK_PATTERNS:
            if re.search(pattern, command_lower):
                score = max(score, 0.5)
                factors.append(f"Matches medium-risk pattern: {pattern}")

        # Configured dangerous patterns
        for pattern in self.dangerous_patterns:
            if pattern.lower() in command_lower:
                score = max(score, 0.7)
                factors.append(f"Matches configured dangerous pattern: '{pattern}'")

        # Pipe complexity adds risk
        pipe_count = command.count("|")
        if pipe_count > 3:
            score = min(score + 0.1, 1.0)
            factors.append(f"Complex pipe chain ({pipe_count} pipes)")

        # Network access
        if self._has_network_access(command):
            score = min(score + 0.2, 1.0)
            factors.append("Network access detected")
            blast_radius = "system"

        # Privilege escalation
        if "sudo" in command_lower or "su " in command_lower:
            score = min(score + 0.3, 1.0)
            factors.append("Privilege escalation requested")
            blast_radius = "system"

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
            mitigation="Review command manually" if score > 0.5 else "Proceed with caution",
            rollback_possible=score < 0.6,
            blast_radius=blast_radius,
        )

    def _has_network_access(self, command: str) -> bool:
        """Heuristically check if a command accesses the network."""
        network_indicators = [
            "curl ", "wget ", "nc ", "ncat ", "telnet ",
            "ssh ", "scp ", "rsync ", "git clone", "git fetch",
            "git pull", "git push", "pip install", "npm install",
            "apt-get", "apt ", "yum ", "dnf ", "brew ",
            "docker pull", "docker run", "kubectl ",
            "http://", "https://", "ftp://",
        ]
        command_lower = command.lower()
        return any(indicator in command_lower for indicator in network_indicators)
