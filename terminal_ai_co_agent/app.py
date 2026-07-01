"""Main application bootstrap — wires all subsystems together."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from terminal_ai_co_agent.ai.providers.ollama import OllamaProvider
from terminal_ai_co_agent.ai.registry import ProviderRegistry
from terminal_ai_co_agent.analysis.dependency import DependencyAnalyzer
from terminal_ai_co_agent.analysis.security import SecurityAnalyzer
from terminal_ai_co_agent.analysis.static import StaticAnalyzer
from terminal_ai_co_agent.config.loader import load_config
from terminal_ai_co_agent.config.types import CoAgentConfig
from terminal_ai_co_agent.context.collector import ContextCollector
from terminal_ai_co_agent.deployment.engine import DeploymentEngine
from terminal_ai_co_agent.executor.engine import ExecutionEngine
from terminal_ai_co_agent.git.client import GitClient
from terminal_ai_co_agent.ide.lsp import LSPBridge
from terminal_ai_co_agent.logging.audit import init_audit
from terminal_ai_co_agent.logging.logger import configure_logging, get_logger
from terminal_ai_co_agent.memory.project_knowledge import ProjectKnowledge
from terminal_ai_co_agent.memory.session import SessionMemory
from terminal_ai_co_agent.memory.store import create_memory_store
from terminal_ai_co_agent.multi_agent.coordinator import MultiAgentCoordinator
from terminal_ai_co_agent.orchestrator.engine import OrchestrationEngine
from terminal_ai_co_agent.planner.engine import PlanningEngine
from terminal_ai_co_agent.planner.risk import RiskAssessor
from terminal_ai_co_agent.plugins.manager import PluginManager
from terminal_ai_co_agent.rag.engine import RAGEngine
from terminal_ai_co_agent.safety.guard import SafetyGuard
from terminal_ai_co_agent.safety.policies.command import CommandSafetyPolicy
from terminal_ai_co_agent.safety.policies.file import FileSafetyPolicy
from terminal_ai_co_agent.safety.rollback import RollbackManager

if TYPE_CHECKING:
    from terminal_ai_co_agent.memory.store import MemoryStore

logger = get_logger(__name__)


class CoAgent:
    """The Terminal AI Co-Agent application.

    This is the central orchestrator that wires together all subsystems.
    It provides a unified API for the CLI and any future interfaces.

    Usage:
        coagent = CoAgent()
        await coagent.initialize()

        # Ask a question
        result = await coagent.ask("How do I add authentication?")

        # Plan a task
        plan = await coagent.plan("Add rate limiting to the API")

        # Execute a plan
        result = await coagent.execute_plan(plan)

        # Shutdown
        await coagent.shutdown()
    """

    def __init__(
        self,
        config_path: Path | str | None = None,
        project_root: Path | None = None,
    ) -> None:
        # ── Configuration ────────────────────────────────────
        self.config: CoAgentConfig = load_config(
            config_path=config_path,
            project_root=project_root,
        )
        self.project_root = Path(self.config.general.project_root).resolve()

        # ── Logging & Audit ──────────────────────────────────
        configure_logging(
            level=self.config.logging.level,  # type: ignore[arg-type]
            json_format=self.config.logging.json_format,
            log_directory=self.config.logging.directory,
        )
        init_audit(
            audit_dir=self.config.logging.directory if self.config.logging.audit else None,
            enabled=self.config.logging.audit,
        )

        # ── AI Providers ─────────────────────────────────────
        self.provider_registry = ProviderRegistry()

        # ── Core Engines (initialized later) ──────────────────
        self.memory_store: MemoryStore | None = None
        self.project_knowledge: ProjectKnowledge | None = None
        self.session_memory: SessionMemory | None = None
        self.safety_guard: SafetyGuard | None = None
        self.file_policy: FileSafetyPolicy | None = None
        self.command_policy: CommandSafetyPolicy | None = None
        self.rollback_manager: RollbackManager | None = None
        self.execution_engine: ExecutionEngine | None = None
        self.git_client: GitClient | None = None
        self.context_collector: ContextCollector | None = None
        self.orchestration_engine: OrchestrationEngine | None = None
        self.planning_engine: PlanningEngine | None = None
        self.risk_assessor: RiskAssessor | None = None
        self.plugin_manager: PluginManager | None = None
        self.rag_engine: RAGEngine | None = None
        self.multi_agent_coordinator: MultiAgentCoordinator | None = None
        self.deployment_engine: DeploymentEngine | None = None
        self.lsp_bridge: LSPBridge | None = None
        self.static_analyzer: StaticAnalyzer | None = None
        self.dependency_analyzer: DependencyAnalyzer | None = None
        self.security_analyzer: SecurityAnalyzer | None = None

        # ── State ────────────────────────────────────────────
        self._initialized = False
        self._session_id: str = ""

        logger.info(
            "coagent.created",
            project_root=str(self.project_root),
            provider=self.config.general.default_provider,
            single_model=self.config.general.single_model_mode,
        )

    # ── Initialization ──────────────────────────────────────────

    async def initialize(self) -> None:
        """Initialize all subsystems in the correct dependency order.

        Order matters:
        1. AI providers (no dependencies)
        2. Memory (no dependencies)
        3. Safety policies (depend on config)
        4. Core engines (depend on providers, memory, safety)
        5. Optional subsystems (plugins, RAG, analysis, IDE, deployment)
        """
        if self._initialized:
            logger.warning("coagent.already_initialized")
            return

        logger.info("coagent.initializing")

        # Phase 1: AI Providers
        await self._init_providers()

        # Phase 2: Memory
        await self._init_memory()

        # Phase 3: Safety
        await self._init_safety()

        # Phase 4: Core Engines
        await self._init_core_engines()

        # Phase 5: Optional Subsystems
        await self._init_optional_subsystems()

        self._initialized = True
        logger.info("coagent.initialized", session_id=self._session_id)

    async def _init_providers(self) -> None:
        """Initialize AI providers from configuration."""
        provider_configs = self.config.providers

        # Always register Ollama if configured
        if "ollama" in provider_configs:
            ollama_config = provider_configs["ollama"]
            provider = OllamaProvider(
                base_url=ollama_config.base_url,
                timeout=ollama_config.timeout,
                retry_attempts=ollama_config.retry_attempts,
                retry_delay=ollama_config.retry_delay,
            )
            self.provider_registry.register(provider)

            # Health check
            healthy = await provider.health_check()
            if healthy:
                logger.info("provider.ollama.healthy")
            else:
                logger.warning("provider.ollama.unreachable", url=ollama_config.base_url)

        # OpenAI provider (if configured with API key)
        if "openai" in provider_configs and provider_configs["openai"].api_key:
            try:
                from terminal_ai_co_agent.ai.providers.openai import OpenAIProvider
                openai_config = provider_configs["openai"]
                provider = OpenAIProvider(
                    base_url=openai_config.base_url,
                    api_key=openai_config.api_key,
                    timeout=openai_config.timeout,
                    retry_attempts=openai_config.retry_attempts,
                )
                self.provider_registry.register(provider)
                logger.info("provider.openai.registered")
            except ImportError:
                logger.debug("provider.openai.skipped", message="openai package not installed")
            except Exception as exc:
                logger.warning("provider.openai.error", error=str(exc))

        # Anthropic provider
        if "anthropic" in provider_configs and provider_configs["anthropic"].api_key:
            try:
                from terminal_ai_co_agent.ai.providers.anthropic import AnthropicProvider
                anthropic_config = provider_configs["anthropic"]
                provider = AnthropicProvider(
                    base_url=anthropic_config.base_url,
                    api_key=anthropic_config.api_key,
                    timeout=anthropic_config.timeout,
                    retry_attempts=anthropic_config.retry_attempts,
                )
                self.provider_registry.register(provider)
                logger.info("provider.anthropic.registered")
            except ImportError:
                logger.debug("provider.anthropic.skipped")
            except Exception as exc:
                logger.warning("provider.anthropic.error", error=str(exc))

        logger.info(
            "providers.initialized",
            count=len(self.provider_registry.provider_names),
            providers=self.provider_registry.provider_names,
        )

    async def _init_memory(self) -> None:
        """Initialize memory subsystem."""
        import uuid

        self._session_id = str(uuid.uuid4())[:8]

        self.memory_store = create_memory_store(self.config.memory)
        await self.memory_store.initialize()

        self.project_knowledge = ProjectKnowledge(
            self.memory_store,
            self.project_root,
        )

        self.session_memory = SessionMemory(
            self.memory_store,
            session_id=self._session_id,
        )

        logger.info("memory.initialized", backend=self.config.memory.backend)

    async def _init_safety(self) -> None:
        """Initialize safety subsystem."""
        self.file_policy = FileSafetyPolicy(self.config.safety)
        self.command_policy = CommandSafetyPolicy(self.config.safety)
        self.safety_guard = SafetyGuard(self.config.safety)
        self.rollback_manager = RollbackManager(self.config.safety)

        logger.info("safety.initialized", mode=self.config.safety.approval_mode)

    async def _init_core_engines(self) -> None:
        """Initialize core engines that depend on providers, memory, and safety."""
        # Execution engine
        self.execution_engine = ExecutionEngine(self.config)
        self.rollback_manager.file_ops = self.execution_engine.file_ops

        # Git client
        self.git_client = GitClient(
            self.config.git,
            self.project_root,
        )

        # Context collector
        self.context_collector = ContextCollector(self.config)

        # Orchestration engine
        self.orchestration_engine = OrchestrationEngine(
            self.config,
            self.provider_registry,
        )

        # Planning engine
        self.planning_engine = PlanningEngine(
            self.config,
            self.provider_registry,
        )

        # Risk assessor
        self.risk_assessor = RiskAssessor(
            self.config.safety,
            self.file_policy,
            self.command_policy,
        )

        # Analysis engines
        self.static_analyzer = StaticAnalyzer()
        self.dependency_analyzer = DependencyAnalyzer(self.project_root)
        self.security_analyzer = SecurityAnalyzer()

        logger.info("core_engines.initialized")

    async def _init_optional_subsystems(self) -> None:
        """Initialize optional subsystems."""
        # Plugin manager
        self.plugin_manager = PluginManager(self.config.plugins)
        if self.config.plugins.enabled:
            await self.plugin_manager.initialize()

        # RAG engine
        self.rag_engine = RAGEngine(self.config)
        if self.config.rag.enabled:
            await self.rag_engine.initialize()
            # Index project in background
            import asyncio
            asyncio.create_task(self.rag_engine.index_project(self.project_root))

        # Multi-agent coordinator
        self.multi_agent_coordinator = MultiAgentCoordinator(
            self.config,
            self.provider_registry,
        )

        # Deployment engine
        self.deployment_engine = DeploymentEngine(self.config)

        # LSP bridge
        self.lsp_bridge = LSPBridge()

        logger.info("optional_subsystems.initialized")

    # ── High-Level API ──────────────────────────────────────────

    async def ask(
        self,
        query: str,
        files: list[Path] | None = None,
        use_rag: bool = True,
    ) -> dict[str, Any]:
        """Ask the Co-Agent a question or request a task.

        This is the primary entry point for natural language interaction.
        """
        self._ensure_initialized()

        logger.info("coagent.ask", query=query[:200])
        await self.session_memory.add_turn("user", query)  # type: ignore[union-attr]

        # Collect context
        context = await self.context_collector.collect_full()  # type: ignore[union-attr]

        if files:
            file_contexts = await self.context_collector.collect_files(files)  # type: ignore[union-attr]
            context.files.extend(file_contexts)

        # Package context
        context_package = self.context_collector.package_for_model(  # type: ignore[union-attr]
            context, query,
            max_tokens=self.config.orchestrator.context_budget,
        )

        # Augment with RAG if available
        if use_rag and self.rag_engine and self.rag_engine.is_ready:
            rag_context = await self.rag_engine.augment_query(query)
            if rag_context != query:
                query = f"{rag_context}\n\n---\n\n{query}"

        # Execute through orchestrator
        result = await self.orchestration_engine.execute_pipeline(  # type: ignore[union-attr]
            task=query,
            context={"context_package": context_package},
        )

        # Store in session
        response_text = result.final_output.get("plan", str(result.final_output))
        await self.session_memory.add_turn("assistant", response_text)  # type: ignore[union-attr]

        return {
            "success": result.success,
            "response": response_text,
            "tokens": result.total_tokens,
            "elapsed_ms": result.elapsed_ms,
            "pipeline_stages": len(result.tasks),
        }

    async def plan(
        self,
        task: str,
        constraints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate a detailed execution plan for a task."""
        self._ensure_initialized()

        logger.info("coagent.plan", task=task[:200])

        # Collect context
        context = await self.context_collector.collect_full()  # type: ignore[union-attr]
        context_package = self.context_collector.package_for_model(  # type: ignore[union-attr]
            context, task,
            max_tokens=self.config.orchestrator.context_budget,
        )

        # Generate plan
        plan = await self.planning_engine.create_plan(  # type: ignore[union-attr]
            task=task,
            context_package=context_package,
            constraints=constraints,
        )

        # Analyze plan
        analysis = await self.planning_engine.analyze_plan(plan)  # type: ignore[union-attr]

        # Assess risks
        risks = self.risk_assessor.assess_plan(plan)  # type: ignore[union-attr]

        return {
            "plan_id": plan.id,
            "summary": plan.summary,
            "steps": [
                {
                    "id": s.id,
                    "type": s.type.value,
                    "description": s.description,
                    "risk": s.risk.value,
                    "dependencies": s.dependencies,
                    "estimated_effort": s.estimated_effort,
                }
                for s in plan.steps
            ],
            "risk_assessment": risks,
            "analysis": analysis,
            "assumptions": plan.assumptions,
            "alternatives": plan.alternatives_considered,
            "status": plan.status.value,
        }

    async def approve_plan(self, plan_id: str) -> bool:
        """Approve a plan for execution."""
        self._ensure_initialized()
        return self.planning_engine.update_status(plan_id, "approved")  # type: ignore[union-attr]

    async def execute_plan(
        self,
        plan_id: str,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Execute an approved plan."""
        self._ensure_initialized()

        plan = self.planning_engine.get_plan(plan_id)  # type: ignore[union-attr]
        if plan is None:
            return {"success": False, "error": f"Plan '{plan_id}' not found"}

        if plan.status.value not in ("approved", "draft"):
            return {
                "success": False,
                "error": f"Plan must be approved before execution. Current status: {plan.status.value}",
            }

        logger.info("coagent.execute", plan_id=plan_id, dry_run=dry_run)

        # Update status
        self.planning_engine.update_status(plan_id, "in_progress")  # type: ignore[union-attr]

        # Convert plan steps to execution operations
        operations = self._plan_to_operations(plan)

        # Execute
        if dry_run:
            self.execution_engine.dry_run = True  # type: ignore[union-attr]

        batch_result = await self.execution_engine.execute_batch(operations)  # type: ignore[union-attr]

        # Record outcome
        if self.project_knowledge:
            await self.project_knowledge.record_change_outcome(
                change_description=plan.task,
                success=batch_result.status.value == "completed",
                lessons=batch_result.results[-1].output if batch_result.results else "",
            )

        # Update plan status
        final_status = "completed" if batch_result.status.value == "completed" else "failed"
        self.planning_engine.update_status(plan_id, final_status)  # type: ignore[union-attr]

        return {
            "success": batch_result.status.value == "completed",
            "plan_id": plan_id,
            "operations": len(batch_result.operations),
            "results": [
                {
                    "operation_id": r.operation_id,
                    "success": r.success,
                    "output": r.output[:500],
                    "error": r.error,
                }
                for r in batch_result.results
            ],
            "status": batch_result.status.value,
        }

    async def review_changes(
        self,
        files: list[str] | None = None,
    ) -> dict[str, Any]:
        """Review current changes in the project."""
        self._ensure_initialized()

        results: dict[str, Any] = {}

        # Git diff
        if self.git_client and await self.git_client.is_repo():
            status = await self.git_client.get_status()
            diff = await self.git_client.get_diff()

            results["git"] = {
                "branch": status.branch,
                "clean": status.clean,
                "staged": len(status.staged),
                "unstaged": len(status.unstaged),
                "untracked": len(status.untracked),
                "diff": diff.diff_text[:2000] if diff else "",
            }

        # Security analysis of changed files
        if files and self.security_analyzer:
            security_results = []
            for f in files:
                path = self.project_root / f
                if path.exists():
                    result = await self.security_analyzer.analyze_file(path)
                    if result.findings:
                        security_results.append({
                            "file": f,
                            "findings": len(result.findings),
                            "critical": sum(
                                1 for finding in result.findings
                                if finding.severity.value == "critical"
                            ),
                        })
            results["security"] = security_results

        return results

    async def rollback(self, steps: int = 1) -> dict[str, Any]:
        """Rollback recent changes."""
        self._ensure_initialized()

        results = []
        for _ in range(steps):
            result = await self.execution_engine.rollback_last()  # type: ignore[union-attr]
            results.extend(result)

        return {
            "success": all(r.success for r in results),
            "operations_rolled_back": len(results),
            "details": [
                {"operation_id": r.operation_id, "success": r.success, "output": r.output}
                for r in results
            ],
        }

    async def analyze_project(
        self,
        analysis_types: list[str] | None = None,
    ) -> dict[str, Any]:
        """Run analysis on the project."""
        self._ensure_initialized()

        types_to_run = analysis_types or ["static", "dependency", "security"]
        results: dict[str, Any] = {}

        if "static" in types_to_run and self.static_analyzer:
            result = await self.static_analyzer.analyze_directory(self.project_root)
            results["static"] = {
                "files_analyzed": result.metadata.get("files_analyzed", 0),
                "findings": len(result.findings),
                "score": result.score,
                "top_issues": [
                    {"file": f.file, "line": f.line, "message": f.message}
                    for f in result.findings[:10]
                ],
            }

        if "dependency" in types_to_run and self.dependency_analyzer:
            result = await self.dependency_analyzer.analyze()
            results["dependency"] = {
                "total_dependencies": result.metadata.get("total_dependencies", 0),
                "findings": len(result.findings),
                "issues": [
                    {"message": f.message, "severity": f.severity.value}
                    for f in result.findings
                ],
            }

        if "security" in types_to_run and self.security_analyzer:
            result = await self.security_analyzer.analyze_directory(self.project_root)
            results["security"] = {
                "files_analyzed": result.metadata.get("files_analyzed", 0),
                "findings": len(result.findings),
                "score": result.score,
                "critical": result.error_count,
            }

        return results

    async def generate_tests(
        self,
        target: str | None = None,
    ) -> dict[str, Any]:
        """Generate tests for project files."""
        self._ensure_initialized()

        # Collect context for the target
        context = await self.context_collector.collect_full()  # type: ignore[union-attr]

        if target:
            target_path = self.project_root / target
            file_contexts = await self.context_collector.collect_files([target_path])  # type: ignore[union-attr]
            context.files = file_contexts

        context_package = self.context_collector.package_for_model(  # type: ignore[union-attr]
            context,
            f"Generate comprehensive tests for {'all files' if not target else target}",
            max_tokens=self.config.orchestrator.context_budget,
        )

        # Use orchestrator with test generation prompt
        result = await self.orchestration_engine.execute_pipeline(  # type: ignore[union-attr]
            task=f"Generate {self.config.testing.framework} tests for {'all project files' if not target else target}. "
                 f"Include edge cases, error handling, and follow existing test patterns.",
            context={"context_package": context_package},
        )

        return {
            "success": result.success,
            "tests": result.final_output.get("plan", ""),
            "tokens": result.total_tokens,
        }

    async def get_status(self) -> dict[str, Any]:
        """Get comprehensive Co-Agent and project status."""
        self._ensure_initialized()

        status: dict[str, Any] = {
            "session_id": self._session_id,
            "initialized": self._initialized,
            "project_root": str(self.project_root),
            "config": {
                "provider": self.config.general.default_provider,
                "single_model": self.config.general.single_model_mode,
                "orchestrator": self.config.orchestrator.enabled,
                "approval_mode": self.config.safety.approval_mode,
            },
            "providers": {},
            "memory": {},
            "git": {},
            "plugins": {},
            "rag": {},
        }

        # Provider status
        health = await self.provider_registry.health_check_all()
        status["providers"] = health

        # Memory stats
        if self.memory_store:
            mem_stats = await self.memory_store.stats()
            status["memory"] = {
                "total_entries": mem_stats.total_entries,
                "entries_by_type": mem_stats.entries_by_type,
                "storage_bytes": mem_stats.storage_bytes,
            }

        # Git status
        if self.git_client and await self.git_client.is_repo():
            git_status = await self.git_client.get_status()
            status["git"] = {
                "branch": git_status.branch,
                "clean": git_status.clean,
                "ahead": git_status.ahead,
                "behind": git_status.behind,
            }

        # Plugin status
        if self.plugin_manager:
            status["plugins"] = {
                "enabled": self.plugin_manager.is_enabled,
                "active": len(self.plugin_manager.active_plugins),
                "list": self.plugin_manager.get_status(),
            }

        # RAG status
        if self.rag_engine:
            status["rag"] = self.rag_engine.get_stats()

        # Safety stats
        if self.safety_guard:
            status["safety"] = self.safety_guard.stats

        return status

    # ── Shutdown ────────────────────────────────────────────────

    async def shutdown(self) -> None:
        """Gracefully shut down all subsystems."""
        logger.info("coagent.shutting_down")

        shutdown_order = [
            ("plugins", self.plugin_manager, "shutdown"),
            ("rag", self.rag_engine, None),
            ("lsp", self.lsp_bridge, "disconnect"),
            ("memory", self.memory_store, "close"),
            ("execution", self.execution_engine, "cleanup"),
        ]

        for name, component, method_name in shutdown_order:
            if component is None:
                continue
            try:
                if method_name:
                    await getattr(component, method_name)()
                logger.debug(f"coagent.shutdown.{name}")
            except Exception as exc:
                logger.warning(f"coagent.shutdown.{name}.error", error=str(exc))

        self._initialized = False
        logger.info("coagent.shutdown_complete")

    # ── Context Manager Support ─────────────────────────────────

    async def __aenter__(self) -> "CoAgent":
        await self.initialize()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.shutdown()

    # ── Helpers ─────────────────────────────────────────────────

    def _ensure_initialized(self) -> None:
        """Raise if not initialized."""
        if not self._initialized:
            raise RuntimeError(
                "CoAgent not initialized. Call `await coagent.initialize()` first, "
                "or use `async with CoAgent() as agent:`."
            )

    def _plan_to_operations(self, plan: Any) -> Any:
        """Convert plan steps to execution operations."""
        from terminal_ai_co_agent.executor.types import (
            CommandOperation,
            ExecutionBatch,
            FileOperation,
            GitOperation,
            OperationType,
        )

        operations: list[FileOperation | CommandOperation | GitOperation] = []

        for step in plan.steps:
            if step.type.value in ("file_create", "file_modify", "file_delete"):
                op_type = {
                    "file_create": OperationType.FILE_CREATE,
                    "file_modify": OperationType.FILE_MODIFY,
                    "file_delete": OperationType.FILE_DELETE,
                }[step.type.value]

                file_path = self.project_root / step.details.get("raw", step.description)

                operations.append(FileOperation(
                    type=op_type,
                    path=file_path,
                    content=step.details.get("content", ""),
                ))

            elif step.type.value == "command":
                operations.append(CommandOperation(
                    command=step.details.get("command", step.description),
                    cwd=self.project_root,
                ))

            elif step.type.value == "git_operation":
                operations.append(GitOperation(
                    type=OperationType.GIT_COMMIT,
                    message=step.description,
                ))

        return ExecutionBatch(
            id=plan.id,
            operations=operations,
        )
