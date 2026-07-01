"""Orchestration engine — coordinates the multi-model pipeline."""

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
from terminal_ai_co_agent.config.types import CoAgentConfig
from terminal_ai_co_agent.logging.audit import audit_event
from terminal_ai_co_agent.logging.logger import get_logger
from terminal_ai_co_agent.orchestrator.types import (
    PipelineResult,
    PipelineStage,
    PipelineTask,
    TaskStatus,
)

if TYPE_CHECKING:
    from terminal_ai_co_agent.ai.registry import ProviderRegistry

logger = get_logger(__name__)


class OrchestrationEngine:
    """Core orchestration engine for the Terminal AI Co-Agent.

    Responsibilities:
    - Coordinate multi-model pipeline execution
    - Route tasks to appropriate models
    - Manage context compression and aggregation
    - Handle retries and fallbacks
    - Track pipeline state and results
    """

    def __init__(
        self,
        config: CoAgentConfig,
        provider_registry: ProviderRegistry,
    ) -> None:
        self.config = config
        self.registry = provider_registry
        self._active_pipelines: dict[str, list[PipelineTask]] = {}

    # ── Pipeline Execution ───────────────────────────────────────

    async def execute_pipeline(
        self,
        task: str,
        context: dict[str, Any] | None = None,
        *,
        use_orchestration: bool | None = None,
    ) -> PipelineResult:
        """Execute the full orchestration pipeline for a given task.

        Args:
            task: The natural language task description.
            context: Pre-collected context (if None, collection stage runs).
            use_orchestration: Override config setting for pipeline mode.

        Returns:
            Complete pipeline result with all task outputs.
        """
        pipeline_id = str(uuid.uuid4())[:8]
        start_time = time.monotonic()

        use_pipeline = use_orchestration if use_orchestration is not None else self.config.orchestrator.enabled

        if not use_pipeline or self.config.general.single_model_mode:
            return await self._execute_single_model(task, context)

        logger.info("pipeline.start", pipeline_id=pipeline_id, task=task[:200])

        tasks: list[PipelineTask] = []
        accumulated_context = context or {}

        # Stage 1: Context Collection (small model)
        if not accumulated_context:
            ctx_task = await self._run_stage(
                pipeline_id=pipeline_id,
                stage=PipelineStage.CONTEXT_COLLECTION,
                model_role=ModelRole.CONTEXT,
                input_data={"task": task},
            )
            tasks.append(ctx_task)
            if ctx_task.status == TaskStatus.COMPLETED:
                accumulated_context.update(ctx_task.output_data)

        # Stage 2: Context Compression (orchestrator-level)
        compress_task = await self._run_stage(
            pipeline_id=pipeline_id,
            stage=PipelineStage.CONTEXT_COMPRESSION,
            model_role=ModelRole.CONTEXT,
            input_data={"context": accumulated_context, "task": task},
        )
        tasks.append(compress_task)
        if compress_task.status == TaskStatus.COMPLETED:
            accumulated_context = compress_task.output_data

        # Stage 3: Planning (reasoning model)
        plan_task = await self._run_stage(
            pipeline_id=pipeline_id,
            stage=PipelineStage.PLANNING,
            model_role=ModelRole.REASONING,
            input_data={"context": accumulated_context, "task": task},
        )
        tasks.append(plan_task)

        # Stage 4: Verification (verification model)
        if plan_task.status == TaskStatus.COMPLETED:
            verify_task = await self._run_stage(
                pipeline_id=pipeline_id,
                stage=PipelineStage.VERIFICATION,
                model_role=ModelRole.VERIFICATION,
                input_data={
                    "context": accumulated_context,
                    "task": task,
                    "plan": plan_task.output_data,
                },
            )
            tasks.append(verify_task)

        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        total_tokens = sum(
            t.output_data.get("tokens", 0) for t in tasks
        )

        success = all(
            t.status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED)
            for t in tasks
        )

        result = PipelineResult(
            success=success,
            tasks=tasks,
            final_output=plan_task.output_data if success else {},
            total_tokens=total_tokens,
            elapsed_ms=elapsed_ms,
            errors=[t.error for t in tasks if t.error],
        )

        audit_event(
            event_type="pipeline_completed",
            pipeline_id=pipeline_id,
            success=success,
            stages=len(tasks),
            tokens=total_tokens,
            elapsed_ms=elapsed_ms,
        )

        logger.info(
            "pipeline.complete",
            pipeline_id=pipeline_id,
            success=success,
            elapsed_ms=elapsed_ms,
        )

        return result

    async def _execute_single_model(
        self,
        task: str,
        context: dict[str, Any] | None = None,
    ) -> PipelineResult:
        """Fallback: execute with a single model."""
        start_time = time.monotonic()
        task_id = str(uuid.uuid4())[:8]

        provider_spec = self.registry.get_model_for_role(ModelRole.DEFAULT)
        if provider_spec is None:
            default_config = self.config.models.default
            provider = self.registry.get(default_config.provider)
            model = default_config.model
        else:
            provider, model = provider_spec

        messages = [
            Message(role=MessageRole.SYSTEM, content="You are an expert software engineer assistant."),
            Message(role=MessageRole.USER, content=task),
        ]

        if context:
            ctx_str = self._format_context(context)
            messages.insert(1, Message(role=MessageRole.USER, content=f"Project context:\n{ctx_str}"))

        request = CompletionRequest(
            messages=messages,
            model=model,
            temperature=0.1,
            max_tokens=4096,
        )

        try:
            response = await provider.complete(request)
            elapsed_ms = int((time.monotonic() - start_time) * 1000)

            pipeline_task = PipelineTask(
                id=task_id,
                stage=PipelineStage.PLANNING,
                status=TaskStatus.COMPLETED,
                model_role=ModelRole.DEFAULT,
                output_data={"plan": response.content, "tokens": response.usage.total_tokens},
            )

            return PipelineResult(
                success=True,
                tasks=[pipeline_task],
                final_output={"plan": response.content},
                total_tokens=response.usage.total_tokens,
                elapsed_ms=elapsed_ms,
            )
        except Exception as exc:
            logger.error("pipeline.single_model.error", error=str(exc))
            pipeline_task = PipelineTask(
                id=task_id,
                stage=PipelineStage.PLANNING,
                status=TaskStatus.FAILED,
                error=str(exc),
            )
            return PipelineResult(
                success=False,
                tasks=[pipeline_task],
                errors=[str(exc)],
            )

    # ── Stage Execution ──────────────────────────────────────────

    async def _run_stage(
        self,
        pipeline_id: str,
        stage: PipelineStage,
        model_role: ModelRole,
        input_data: dict[str, Any],
    ) -> PipelineTask:
        """Execute a single pipeline stage."""
        task = PipelineTask(
            id=f"{pipeline_id}-{stage.value}",
            stage=stage,
            model_role=model_role,
            input_data=input_data,
            status=TaskStatus.RUNNING,
        )

        logger.debug("pipeline.stage.start", pipeline_id=pipeline_id, stage=stage.value)

        try:
            output = await self._execute_model_for_stage(stage, model_role, input_data)
            task.status = TaskStatus.COMPLETED
            task.output_data = output
        except Exception as exc:
            logger.error("pipeline.stage.error", pipeline_id=pipeline_id, stage=stage.value, error=str(exc))
            task.status = TaskStatus.FAILED
            task.error = str(exc)

        return task

    async def _execute_model_for_stage(
        self,
        stage: PipelineStage,
        model_role: ModelRole,
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute the appropriate model for a pipeline stage."""
        provider_spec = self.registry.get_model_for_role(model_role)
        if provider_spec is None:
            # Fallback to config-defined models
            model_config = getattr(self.config.models, model_role.value)
            provider = self.registry.get(model_config.provider)
            model = model_config.model
            system_prompt = model_config.system_prompt
        else:
            provider, model = provider_spec
            system_prompt = ""

        # Build prompt based on stage
        stage_prompts = {
            PipelineStage.CONTEXT_COLLECTION: "Extract and summarize the relevant context from the project files.",
            PipelineStage.CONTEXT_COMPRESSION: "Compress and organize the following context, removing redundancy.",
            PipelineStage.PLANNING: "Create a detailed execution plan based on the context and task.",
            PipelineStage.VERIFICATION: "Review the proposed plan for correctness, safety, and completeness.",
        }

        messages = [
            Message(role=MessageRole.SYSTEM, content=system_prompt or stage_prompts.get(stage, "")),
            Message(role=MessageRole.USER, content=str(input_data)),
        ]

        request = CompletionRequest(
            messages=messages,
            model=model,
            temperature=0.0 if stage != PipelineStage.PLANNING else 0.1,
            max_tokens=2048 if stage != PipelineStage.PLANNING else 4096,
        )

        response = await provider.complete(request)

        return {
            f"{stage.value}_output": response.content,
            "tokens": response.usage.total_tokens,
            "model": response.model,
        }

    # ── Helpers ──────────────────────────────────────────────────

    def _format_context(self, context: dict[str, Any]) -> str:
        """Format context dict into a string for model consumption."""
        import json
        return json.dumps(context, indent=2, default=str)

    def cancel_pipeline(self, pipeline_id: str) -> None:
        """Cancel a running pipeline."""
        if pipeline_id in self._active_pipelines:
            for task in self._active_pipelines[pipeline_id]:
                if task.status == TaskStatus.RUNNING:
                    task.status = TaskStatus.CANCELLED
            logger.info("pipeline.cancelled", pipeline_id=pipeline_id)
            audit_event("pipeline_cancelled", pipeline_id=pipeline_id)
