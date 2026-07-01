"""Task decomposition — breaks complex tasks into manageable subtasks."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from terminal_ai_co_agent.logging.logger import get_logger
from terminal_ai_co_agent.planner.types import (
    ExecutionPlan,
    PlanStatus,
    PlanStep,
    RiskLevel,
    StepType,
)

if TYPE_CHECKING:
    from terminal_ai_co_agent.context.types import ContextPackage

logger = get_logger(__name__)


class TaskDecomposer:
    """Decomposes complex tasks into subtasks.

    Handles:
    - Breaking large changes into smaller steps
    - Grouping related file modifications
    - Ordering steps by dependency
    - Separating analysis, implementation, and validation phases
    """

    # Patterns that indicate a task should be decomposed
    COMPLEXITY_INDICATORS = [
        "refactor", "migrate", "restructure", "implement",
        "add feature", "integrate", "overhaul", "redesign",
        "multiple files", "across the project", "entire",
    ]

    def __init__(self) -> None:
        pass

    def should_decompose(self, task: str) -> bool:
        """Determine if a task likely needs decomposition."""
        task_lower = task.lower()
        return any(indicator in task_lower for indicator in self.COMPLEXITY_INDICATORS)

    async def decompose_plan(
        self,
        plan: ExecutionPlan,
        max_steps_per_subtask: int = 5,
    ) -> list[ExecutionPlan]:
        """Decompose a large plan into smaller sub-plans.

        Grouping strategy:
        1. Analysis/investigation steps
        2. Core implementation steps
        3. Testing steps
        4. Documentation steps
        5. Cleanup/finalization steps
        """
        subtasks: list[ExecutionPlan] = []

        # Phase 1: Analysis
        analysis_steps = [
            s for s in plan.steps
            if s.type in (StepType.ANALYSIS, StepType.REVIEW)
        ]
        if analysis_steps:
            subtasks.append(self._create_sub_plan(plan, analysis_steps, "Analysis", 1))

        # Phase 2: Core Implementation (grouped by directory/module)
        impl_steps = [
            s for s in plan.steps
            if s.type in (StepType.FILE_CREATE, StepType.FILE_MODIFY, StepType.FILE_DELETE, StepType.PATCH)
        ]
        grouped = self._group_by_module(impl_steps)

        for i, (module, steps) in enumerate(grouped.items()):
            if len(steps) <= max_steps_per_subtask:
                subtasks.append(
                    self._create_sub_plan(plan, steps, f"Implement: {module}", 2 + i)
                )
            else:
                # Split large group further
                for j in range(0, len(steps), max_steps_per_subtask):
                    chunk = steps[j:j + max_steps_per_subtask]
                    subtasks.append(
                        self._create_sub_plan(
                            plan, chunk,
                            f"Implement: {module} (part {j // max_steps_per_subtask + 1})",
                            2 + i + j,
                        )
                    )

        # Phase 3: Commands / Git
        cmd_steps = [
            s for s in plan.steps
            if s.type in (StepType.COMMAND, StepType.GIT_OPERATION, StepType.DEPLOYMENT)
        ]
        if cmd_steps:
            subtasks.append(self._create_sub_plan(plan, cmd_steps, "Commands & Operations", 90))

        # Phase 4: Testing
        test_steps = [s for s in plan.steps if s.type == StepType.TEST]
        if test_steps:
            subtasks.append(self._create_sub_plan(plan, test_steps, "Testing", 95))

        # Phase 5: Documentation
        doc_steps = [s for s in plan.steps if s.type == StepType.DOCUMENTATION]
        if doc_steps:
            subtasks.append(self._create_sub_plan(plan, doc_steps, "Documentation", 98))

        logger.info(
            "planner.decomposed",
            original_plan=plan.id,
            subtasks=len(subtasks),
        )

        return subtasks

    def create_checkpoint_plan(
        self,
        plan: ExecutionPlan,
        checkpoint_name: str,
    ) -> ExecutionPlan:
        """Create a minimal checkpoint plan (just a marker step)."""
        return ExecutionPlan(
            id=str(uuid.uuid4())[:8],
            task=f"Checkpoint: {checkpoint_name}",
            summary=f"Create checkpoint '{checkpoint_name}' before proceeding",
            steps=[
                PlanStep(
                    id="checkpoint",
                    type=StepType.ANALYSIS,
                    description=f"Create checkpoint: {checkpoint_name}",
                    risk=RiskLevel.NONE,
                    estimated_effort="small",
                )
            ],
            status=PlanStatus.DRAFT,
        )

    def _create_sub_plan(
        self,
        parent: ExecutionPlan,
        steps: list[PlanStep],
        phase_name: str,
        order: int,
    ) -> ExecutionPlan:
        """Create a sub-plan from a set of steps."""
        # Rewrite dependencies to be relative to sub-plan
        step_ids = {s.id for s in steps}
        rewritten_steps = []
        for step in steps:
            new_deps = [d for d in step.dependencies if d in step_ids]
            rewritten_steps.append(PlanStep(
                id=step.id,
                type=step.type,
                description=step.description,
                details=step.details,
                dependencies=new_deps,
                risk=step.risk,
                estimated_effort=step.estimated_effort,
                rollback_instructions=step.rollback_instructions,
                alternatives=step.alternatives,
            ))

        return ExecutionPlan(
            id=str(uuid.uuid4())[:8],
            task=f"[{order}] {phase_name}",
            summary=f"Sub-plan for {phase_name}: {parent.task[:100]}",
            steps=rewritten_steps,
            status=PlanStatus.DRAFT,
            risk_assessment=parent.risk_assessment,
            metadata={
                "parent_plan_id": parent.id,
                "phase": phase_name,
                "order": order,
            },
        )

    def _group_by_module(
        self,
        steps: list[PlanStep],
    ) -> dict[str, list[PlanStep]]:
        """Group steps by the module/directory they affect."""
        import re
        from pathlib import Path

        groups: dict[str, list[PlanStep]] = {}

        for step in steps:
            # Try to extract a file path from details
            details_raw = step.details.get("raw", "") if isinstance(step.details, dict) else str(step.details)
            description = step.description

            path_match = re.search(r'[\w./-]+\.\w{1,6}', description + " " + details_raw)
            if path_match:
                path_str = path_match.group()
                try:
                    module = str(Path(path_str).parent) or Path(path_str).stem
                except Exception:
                    module = "other"
            else:
                module = "other"

            groups.setdefault(module, []).append(step)

        return groups
