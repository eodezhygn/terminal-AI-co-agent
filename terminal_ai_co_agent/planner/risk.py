"""Risk assessment for plan steps."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from terminal_ai_co_agent.planner.types import (
    ExecutionPlan,
    PlanStep,
    RiskLevel,
    StepType,
)

if TYPE_CHECKING:
    from terminal_ai_co_agent.config.types import SafetyConfig
    from terminal_ai_co_agent.safety.policies.command import CommandSafetyPolicy
    from terminal_ai_co_agent.safety.policies.file import FileSafetyPolicy


class RiskAssessor:
    """Assesses and explains risks for plan steps."""

    def __init__(
        self,
        safety_config: "SafetyConfig",
        file_policy: "FileSafetyPolicy",
        command_policy: "CommandSafetyPolicy",
    ) -> None:
        self.safety_config = safety_config
        self.file_policy = file_policy
        self.command_policy = command_policy

    def assess_step(self, step: PlanStep) -> RiskLevel:
        """Assess the risk of a single plan step."""
        # Use safety policies to assess risk
        if step.type in (StepType.FILE_CREATE, StepType.FILE_MODIFY, StepType.FILE_DELETE):
            path_str = self._extract_path(step)
            if path_str:
                try:
                    assessment = self.file_policy.assess_risk(Path(path_str), step.type.value)
                    return assessment.level
                except Exception:
                    pass

        elif step.type == StepType.COMMAND:
            command = step.details.get("command", "") if isinstance(step.details, dict) else ""
            if command:
                try:
                    assessment = self.command_policy.assess_risk(command)
                    return assessment.level
                except Exception:
                    pass

        elif step.type == StepType.GIT_OPERATION:
            # Git operations can be high risk
            description = step.description.lower()
            if "force" in description or "hard reset" in description:
                return RiskLevel.HIGH
            return RiskLevel.MEDIUM

        elif step.type in (StepType.DEPLOYMENT,):
            return RiskLevel.HIGH

        # Default: use step's declared risk or estimate from description
        if step.risk != RiskLevel.NONE:
            return step.risk

        return self._estimate_from_description(step.description)

    def assess_plan(self, plan: ExecutionPlan) -> dict[str, Any]:
        """Assess overall plan risk."""
        step_risks = [self.assess_step(s) for s in plan.steps]

        risk_scores = {
            RiskLevel.NONE: 0,
            RiskLevel.LOW: 1,
            RiskLevel.MEDIUM: 2,
            RiskLevel.HIGH: 3,
            RiskLevel.CRITICAL: 4,
        }

        scores = [risk_scores[r] for r in step_risks]
        avg_score = sum(scores) / len(scores) if scores else 0

        if avg_score >= 3.5:
            overall = RiskLevel.CRITICAL
        elif avg_score >= 2.5:
            overall = RiskLevel.HIGH
        elif avg_score >= 1.5:
            overall = RiskLevel.MEDIUM
        elif avg_score >= 0.5:
            overall = RiskLevel.LOW
        else:
            overall = RiskLevel.NONE

        # Generate risk breakdown
        distribution = {r.value: step_risks.count(r) for r in RiskLevel}

        # Identify highest risk steps
        high_risk = [
            {
                "step_id": step.id,
                "description": step.description[:100],
                "risk": risk.value,
            }
            for step, risk in zip(plan.steps, step_risks)
            if risk in (RiskLevel.HIGH, RiskLevel.CRITICAL)
        ]

        return {
            "overall": overall.value,
            "average_score": round(avg_score, 2),
            "max_score": max(scores) if scores else 0,
            "distribution": distribution,
            "high_risk_steps": high_risk,
            "rollback_possible": all(
                s.rollback_instructions
                for s, r in zip(plan.steps, step_risks)
                if r in (RiskLevel.HIGH, RiskLevel.CRITICAL)
            ),
            "recommendations": self._generate_recommendations(high_risk),
        }

    def _extract_path(self, step: PlanStep) -> str | None:
        """Extract file path from step details or description."""
        import re

        details_raw = step.details.get("raw", "") if isinstance(step.details, dict) else str(step.details)
        text = step.description + " " + details_raw

        match = re.search(r'[\w./-]+\.\w{1,6}', text)
        return match.group() if match else None

    def _estimate_from_description(self, description: str) -> RiskLevel:
        """Estimate risk from step description keywords."""
        desc_lower = description.lower()

        critical_keywords = ["delete all", "drop database", "rm -rf", "production"]
        high_keywords = ["delete", "remove", "drop", "migrate", "restructure", "force push"]
        medium_keywords = ["modify", "change", "update", "refactor", "move"]
        low_keywords = ["create", "add", "document", "test", "format"]

        if any(kw in desc_lower for kw in critical_keywords):
            return RiskLevel.CRITICAL
        if any(kw in desc_lower for kw in high_keywords):
            return RiskLevel.HIGH
        if any(kw in desc_lower for kw in medium_keywords):
            return RiskLevel.MEDIUM
        if any(kw in desc_lower for kw in low_keywords):
            return RiskLevel.LOW

        return RiskLevel.LOW

    def _generate_recommendations(
        self,
        high_risk_steps: list[dict[str, str]],
    ) -> list[str]:
        """Generate safety recommendations for high-risk steps."""
        recommendations: list[str] = []

        if not high_risk_steps:
            return ["No high-risk steps identified."]

        recommendations.append(
            f"{len(high_risk_steps)} high-risk step(s) identified. Review carefully."
        )
        recommendations.append("Ensure backups exist before executing high-risk steps.")
        recommendations.append("Consider running in dry-run mode first.")
        recommendations.append("Execute high-risk steps one at a time with verification between.")

        return recommendations
