"""Planning engine — generates structured execution plans from tasks."""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING, Any

from terminal_ai_co_agent.ai.types import (
    CompletionRequest,
    Message,
    MessageRole,
    ModelRole,
)
from terminal_ai_co_agent.logging.audit import audit_event
from terminal_ai_co_agent.logging.logger import get_logger
from terminal_ai_co_agent.planner.types import (
    ExecutionPlan,
    PlanStatus,
    PlanStep,
    RiskLevel,
    StepType,
)

if TYPE_CHECKING:
    from terminal_ai_co_agent.ai.registry import ProviderRegistry
    from terminal_ai_co_agent.config.types import CoAgentConfig
    from terminal_ai_co_agent.context.types import ContextPackage

logger = get_logger(__name__)


class PlanningEngine:
    """Generates and manages execution plans.

    Works with the reasoning model to:
    - Decompose tasks into executable steps
    - Assess risk for each step
    - Define dependencies between steps
    - Generate alternatives
    - Validate plan feasibility
    """

    def __init__(
        self,
        config: "CoAgentConfig",
        provider_registry: "ProviderRegistry",
    ) -> None:
        self.config = config
        self.registry = provider_registry
        self._plans: dict[str, ExecutionPlan] = {}

    # ── Plan Generation ─────────────────────────────────────────

    async def create_plan(
        self,
        task: str,
        context_package: "ContextPackage",
        *,
        constraints: dict[str, Any] | None = None,
    ) -> ExecutionPlan:
        """Generate an execution plan for a task.

        Args:
            task: Natural language task description.
            context_package: Structured project context.
            constraints: Optional constraints (e.g., "don't modify X").

        Returns:
            A structured ExecutionPlan with ordered steps.
        """
        plan_id = str(uuid.uuid4())[:8]
        logger.info("planner.creating", plan_id=plan_id, task=task[:200])

        # Get reasoning model
        provider_spec = self.registry.get_model_for_role(ModelRole.REASONING)
        if provider_spec:
            provider, model = provider_spec
        else:
            provider = self.registry.get(self.config.models.reasoning.provider)
            model = self.config.models.reasoning.model

        # Build planning prompt
        prompt = self._build_planning_prompt(task, context_package, constraints)
        messages = [
            Message(role=MessageRole.SYSTEM, content=self.config.models.reasoning.system_prompt),
            Message(role=MessageRole.USER, content=prompt),
        ]

        request = CompletionRequest(
            messages=messages,
            model=model,
            temperature=0.1,
            max_tokens=4096,
        )

        response = await provider.complete(request)

        # Parse response into structured plan
        plan = self._parse_plan_response(plan_id, task, response.content)
        plan.status = PlanStatus.PROPOSED
        plan.created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")

        self._plans[plan_id] = plan

        audit_event(
            "plan_created",
            plan_id=plan_id,
            task=task[:200],
            steps=len(plan.steps),
        )

        logger.info(
            "planner.created",
            plan_id=plan_id,
            steps=len(plan.steps),
            risk=plan.risk_assessment.get("overall", "unknown"),
        )

        return plan

    # ── Plan Refinement ─────────────────────────────────────────

    async def refine_plan(
        self,
        plan: ExecutionPlan,
        feedback: str,
    ) -> ExecutionPlan:
        """Refine a plan based on human feedback."""
        logger.info("planner.refining", plan_id=plan.id, feedback=feedback[:200])

        provider_spec = self.registry.get_model_for_role(ModelRole.REASONING)
        if provider_spec:
            provider, model = provider_spec
        else:
            provider = self.registry.get(self.config.models.reasoning.provider)
            model = self.config.models.reasoning.model

        plan_text = self._format_plan_for_model(plan)
        prompt = (
            f"Refine the following plan based on this feedback:\n"
            f"Feedback: {feedback}\n\n"
            f"Original plan:\n{plan_text}\n\n"
            f"Output the refined plan in the same format, incorporating the feedback."
        )

        messages = [
            Message(role=MessageRole.SYSTEM, content=self.config.models.reasoning.system_prompt),
            Message(role=MessageRole.USER, content=prompt),
        ]

        request = CompletionRequest(
            messages=messages,
            model=model,
            temperature=0.1,
            max_tokens=4096,
        )

        response = await provider.complete(request)
        refined = self._parse_plan_response(plan.id, plan.task, response.content)
        refined.status = PlanStatus.PROPOSED
        refined.created_at = plan.created_at

        self._plans[plan.id] = refined

        audit_event("plan_refined", plan_id=plan.id, feedback=feedback[:200])
        return refined

    # ── Plan Analysis (No LLM Required) ─────────────────────────

    async def analyze_plan(self, plan: ExecutionPlan) -> dict[str, Any]:
        """Analyze a plan for structural issues without using an LLM.

        Checks:
        - Circular dependencies
        - Missing dependencies
        - Risk distribution
        - Step ordering sanity
        """
        issues: list[str] = []
        warnings: list[str] = []

        step_ids = {s.id for s in plan.steps}

        # Check for circular dependencies
        for step in plan.steps:
            for dep_id in step.dependencies:
                if dep_id not in step_ids:
                    issues.append(f"Step '{step.id}' depends on nonexistent step '{dep_id}'")

                # Check if dependency creates a cycle
                if self._creates_cycle(step.id, dep_id, plan.steps):
                    issues.append(f"Circular dependency: {step.id} ↔ {dep_id}")

        # Check risk distribution
        high_risk_steps = [s for s in plan.steps if s.risk in (RiskLevel.HIGH, RiskLevel.CRITICAL)]
        if len(high_risk_steps) > len(plan.steps) * 0.5:
            warnings.append(f"{len(high_risk_steps)}/{len(plan.steps)} steps are high risk")

        # Check for orphan steps (no dependencies and nothing depends on them)
        has_dependents = set()
        for step in plan.steps:
            for dep in step.dependencies:
                has_dependents.add(dep)

        orphans = [s for s in plan.steps if not s.dependencies and s.id not in has_dependents]
        if len(orphans) > 1:
            warnings.append(f"{len(orphans)} steps have no dependencies and nothing depends on them")

        # Validate step ordering
        risk_order = {RiskLevel.NONE: 0, RiskLevel.LOW: 1, RiskLevel.MEDIUM: 2, RiskLevel.HIGH: 3, RiskLevel.CRITICAL: 4}
        for i, step in enumerate(plan.steps):
            for dep_id in step.dependencies:
                dep_step = next((s for s in plan.steps if s.id == dep_id), None)
                if dep_step:
                    dep_idx = plan.steps.index(dep_step)
                    if dep_idx > i:
                        warnings.append(f"Step '{step.id}' appears before its dependency '{dep_id}'")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "total_steps": len(plan.steps),
            "risk_distribution": {
                r.value: len([s for s in plan.steps if s.risk == r])
                for r in RiskLevel
            },
        }

    # ── Plan Management ─────────────────────────────────────────

    def get_plan(self, plan_id: str) -> ExecutionPlan | None:
        """Retrieve a plan by ID."""
        return self._plans.get(plan_id)

    def get_all_plans(self, status: PlanStatus | None = None) -> list[ExecutionPlan]:
        """Get all plans, optionally filtered by status."""
        plans = list(self._plans.values())
        if status:
            plans = [p for p in plans if p.status == status]
        return sorted(plans, key=lambda p: p.created_at, reverse=True)

    def update_status(self, plan_id: str, status: PlanStatus) -> bool:
        """Update the status of a plan."""
        plan = self._plans.get(plan_id)
        if not plan:
            return False

        plan.status = status
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ")

        if status == PlanStatus.APPROVED:
            plan.approved_at = now
        elif status == PlanStatus.COMPLETED:
            plan.completed_at = now

        logger.info("planner.status_updated", plan_id=plan_id, status=status.value)
        audit_event("plan_status_changed", plan_id=plan_id, status=status.value)

        return True

    def delete_plan(self, plan_id: str) -> bool:
        """Delete a plan."""
        if plan_id in self._plans:
            del self._plans[plan_id]
            logger.info("planner.deleted", plan_id=plan_id)
            return True
        return False

    # ── Helpers ─────────────────────────────────────────────────

    def _build_planning_prompt(
        self,
        task: str,
        context: "ContextPackage",
        constraints: dict[str, Any] | None = None,
    ) -> str:
        """Build the planning prompt for the reasoning model."""
        parts = [
            "# Task",
            task,
            "",
            "# Project Context",
            f"Project: {context.project_summary}",
            f"Language: {context.metadata.get('language', 'unknown')}",
            f"Framework: {context.metadata.get('framework', 'none')}",
            "",
            "# Project Structure",
            context.structure_overview,
            "",
            "# Relevant Files",
        ]

        for f in context.relevant_files[:15]:
            parts.append(f"## {f.path}")
            parts.append(f"Summary: {f.summary}")
            if f.symbols:
                symbols_str = ", ".join(
                    f"{s.kind} {s.name}" for s in f.symbols[:10]
                )
                parts.append(f"Symbols: {symbols_str}")
            parts.append("")

        parts.append("# Coding Conventions")
        for key, value in context.conventions.items():
            parts.append(f"- {key}: {value}")
        parts.append("")

        if context.recent_changes:
            parts.append("# Recent Changes")
            parts.append(context.recent_changes)
            parts.append("")

        if constraints:
            parts.append("# Constraints")
            for key, value in constraints.items():
                parts.append(f"- {key}: {value}")
            parts.append("")

        parts.extend([
            "# Instructions",
            "Create a detailed execution plan with the following format:",
            "",
            "## Summary",
            "Brief summary of the approach.",
            "",
            "## Assumptions",
            "- List assumptions made",
            "",
            "## Steps",
            "For each step, provide:",
            "- **ID**: unique step identifier",
            "- **Type**: file_create | file_modify | file_delete | command | patch | analysis | review | test | documentation",
            "- **Description**: what this step does",
            "- **Dependencies**: list of step IDs this depends on",
            "- **Risk**: none | low | medium | high | critical",
            "- **Effort**: small | medium | large",
            "- **Details**: specific file paths, commands, or content",
            "- **Rollback**: how to undo this step",
            "- **Alternatives**: other ways to achieve this",
            "",
            "## Risk Assessment",
            "Overall risk level and key concerns.",
            "",
            "## Alternatives Considered",
            "Other approaches that were considered and why they were rejected.",
            "",
            "Output the plan in a clear, structured format.",
        ])

        return "\n".join(parts)

    def _parse_plan_response(
        self,
        plan_id: str,
        task: str,
        response_text: str,
    ) -> ExecutionPlan:
        """Parse the model's response into a structured ExecutionPlan."""
        plan = ExecutionPlan(
            id=plan_id,
            task=task,
            summary="",
        )

        # Extract summary
        if "## Summary" in response_text:
            section = self._extract_section(response_text, "## Summary", "## ")
            plan.summary = section.strip()

        # Extract assumptions
        if "## Assumptions" in response_text:
            section = self._extract_section(response_text, "## Assumptions", "## ")
            plan.assumptions = [
                line.strip("- ").strip()
                for line in section.splitlines()
                if line.strip().startswith("-")
            ]

        # Extract steps
        if "## Steps" in response_text:
            section = self._extract_section(response_text, "## Steps", "## ")
            plan.steps = self._parse_steps(section)

        # Extract risk assessment
        if "## Risk Assessment" in response_text:
            section = self._extract_section(response_text, "## Risk Assessment", "## ")
            plan.risk_assessment = {"assessment": section.strip()}

        # Extract alternatives considered
        if "## Alternatives Considered" in response_text:
            section = self._extract_section(response_text, "## Alternatives Considered", "## ")
            plan.alternatives_considered = [
                line.strip("- ").strip()
                for line in section.splitlines()
                if line.strip().startswith("-")
            ]

        return plan

    def _parse_steps(self, steps_text: str) -> list[PlanStep]:
        """Parse individual steps from the steps section."""
        steps: list[PlanStep] = []
        current_step: dict[str, Any] = {}
        current_field: str = ""

        for line in steps_text.splitlines():
            line = line.strip()
            if not line:
                if current_step and "id" in current_step:
                    steps.append(self._dict_to_step(current_step))
                    current_step = {}
                continue

            # Detect new step
            if line.startswith("**ID**") or line.startswith("- **ID**"):
                if current_step and "id" in current_step:
                    steps.append(self._dict_to_step(current_step))
                    current_step = {}

            # Parse fields
            field_mapping = {
                "**ID**": "id",
                "**Type**": "type",
                "**Description**": "description",
                "**Dependencies**": "dependencies",
                "**Risk**": "risk",
                "**Effort**": "effort",
                "**Details**": "details",
                "**Rollback**": "rollback",
                "**Alternatives**": "alternatives",
            }

            for marker, field in field_mapping.items():
                if marker in line:
                    current_field = field
                    value = line.split(marker, 1)[-1].strip().lstrip(":").strip()
                    current_step[field] = value
                    break

        # Don't forget the last step
        if current_step and "id" in current_step:
            steps.append(self._dict_to_step(current_step))

        return steps

    def _dict_to_step(self, data: dict[str, Any]) -> PlanStep:
        """Convert parsed dict to PlanStep."""
        risk_map = {
            "none": RiskLevel.NONE, "low": RiskLevel.LOW,
            "medium": RiskLevel.MEDIUM, "high": RiskLevel.HIGH,
            "critical": RiskLevel.CRITICAL,
        }
        type_map = {
            "file_create": StepType.FILE_CREATE, "file_modify": StepType.FILE_MODIFY,
            "file_delete": StepType.FILE_DELETE, "command": StepType.COMMAND,
            "patch": StepType.PATCH, "analysis": StepType.ANALYSIS,
            "review": StepType.REVIEW, "test": StepType.TEST,
            "documentation": StepType.DOCUMENTATION, "git_operation": StepType.GIT_OPERATION,
            "deployment": StepType.DEPLOYMENT,
        }

        deps_str = data.get("dependencies", "")
        dependencies = [d.strip() for d in deps_str.replace("none", "").split(",") if d.strip()]

        return PlanStep(
            id=data.get("id", str(uuid.uuid4())[:8]),
            type=type_map.get(data.get("type", "").lower(), StepType.ANALYSIS),
            description=data.get("description", ""),
            details={"raw": data.get("details", "")},
            dependencies=dependencies,
            risk=risk_map.get(data.get("risk", "").lower(), RiskLevel.LOW),
            estimated_effort=data.get("effort", "small").lower(),
            rollback_instructions=data.get("rollback", ""),
            alternatives=[a.strip() for a in data.get("alternatives", "").split(",") if a.strip()],
        )

    def _format_plan_for_model(self, plan: ExecutionPlan) -> str:
        """Format a plan as text for the model to refine."""
        parts = [
            f"Task: {plan.task}",
            f"Summary: {plan.summary}",
            "",
            "Steps:",
        ]
        for step in plan.steps:
            parts.extend([
                f"- ID: {step.id}",
                f"  Type: {step.type.value}",
                f"  Description: {step.description}",
                f"  Risk: {step.risk.value}",
                f"  Dependencies: {', '.join(step.dependencies) or 'none'}",
                f"  Details: {step.details.get('raw', '')}",
                "",
            ])
        return "\n".join(parts)

    def _extract_section(self, text: str, header: str, next_header: str = "## ") -> str:
        """Extract a section between headers."""
        start = text.find(header)
        if start == -1:
            return ""

        start += len(header)
        # Find next header
        remaining = text[start:]
        next_idx = remaining.find(next_header)
        if next_idx == -1:
            return remaining.strip()

        return remaining[:next_idx].strip()

    def _creates_cycle(
        self,
        step_id: str,
        dep_id: str,
        steps: list[PlanStep],
        visited: set | None = None,
    ) -> bool:
        """Check if adding a dependency would create a cycle."""
        if visited is None:
            visited = set()

        if dep_id == step_id:
            return True
        if dep_id in visited:
            return False

        visited.add(dep_id)

        # Find the dependency step and check its dependencies
        dep_step = next((s for s in steps if s.id == dep_id), None)
        if dep_step:
            for transitive_dep in dep_step.dependencies:
                if self._creates_cycle(step_id, transitive_dep, steps, visited.copy()):
                    return True

        return False
