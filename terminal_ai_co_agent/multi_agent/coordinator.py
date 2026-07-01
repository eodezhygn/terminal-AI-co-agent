"""Multi-agent coordinator for complex task orchestration."""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING, Any

from terminal_ai_co_agent.ai.types import (
    CompletionRequest,
    Message,
    MessageRole,
)
from terminal_ai_co_agent.logging.logger import get_logger
from terminal_ai_co_agent.multi_agent.types import (
    AgentDefinition,
    AgentMessage,
    AgentRole,
    AgentStatus,
    CollaborationSession,
)

if TYPE_CHECKING:
    from terminal_ai_co_agent.ai.registry import ProviderRegistry
    from terminal_ai_co_agent.config.types import CoAgentConfig

logger = get_logger(__name__)


class MultiAgentCoordinator:
    """Coordinates multiple specialized agents for complex tasks.

    Enables:
    - Task decomposition to specialized agents
    - Inter-agent communication
    - Result aggregation
    - Consensus building
    - Conflict resolution

    Note: This is a framework for future multi-agent workflows.
    Initial implementation supports coordinator + single worker pattern.
    """

    # Default agent definitions
    DEFAULT_AGENTS: dict[AgentRole, AgentDefinition] = {
        AgentRole.ARCHITECT: AgentDefinition(
            name="Architect",
            role=AgentRole.ARCHITECT,
            description="Designs system architecture and makes high-level decisions",
            capabilities=["architecture_design", "technology_selection", "tradeoff_analysis"],
            system_prompt="You are a software architect. Design clean, scalable solutions.",
        ),
        AgentRole.DEVELOPER: AgentDefinition(
            name="Developer",
            role=AgentRole.DEVELOPER,
            description="Implements code changes and features",
            capabilities=["code_generation", "refactoring", "debugging"],
            system_prompt="You are a senior developer. Write clean, well-tested code.",
        ),
        AgentRole.REVIEWER: AgentDefinition(
            name="Reviewer",
            role=AgentRole.REVIEWER,
            description="Reviews code for quality, security, and correctness",
            capabilities=["code_review", "security_audit", "style_check"],
            system_prompt="You are a thorough code reviewer. Find issues and suggest improvements.",
        ),
        AgentRole.TESTER: AgentDefinition(
            name="Tester",
            role=AgentRole.TESTER,
            description="Creates and runs tests",
            capabilities=["test_generation", "test_execution", "coverage_analysis"],
            system_prompt="You are a test engineer. Write comprehensive tests.",
        ),
        AgentRole.SECURITY_AUDITOR: AgentDefinition(
            name="Security Auditor",
            role=AgentRole.SECURITY_AUDITOR,
            description="Audits code for security vulnerabilities",
            capabilities=["vulnerability_scan", "compliance_check", "threat_modeling"],
            system_prompt="You are a security expert. Identify vulnerabilities and suggest fixes.",
        ),
    }

    def __init__(
        self,
        config: "CoAgentConfig",
        provider_registry: "ProviderRegistry",
    ) -> None:
        self.config = config
        self.registry = provider_registry
        self._agents: dict[str, AgentDefinition] = {}
        self._sessions: dict[str, CollaborationSession] = {}
        self._message_queue: dict[str, list[AgentMessage]] = {}

    # ── Agent Management ────────────────────────────────────────

    def register_agent(self, agent: AgentDefinition) -> None:
        """Register a custom agent."""
        self._agents[agent.name] = agent
        logger.info("multi_agent.registered", name=agent.name, role=agent.role.value)

    def get_default_agents(self, *roles: AgentRole) -> list[AgentDefinition]:
        """Get default agent definitions for roles."""
        return [self.DEFAULT_AGENTS[r] for r in roles if r in self.DEFAULT_AGENTS]

    # ── Collaboration ───────────────────────────────────────────

    async def start_collaboration(
        self,
        task: str,
        agents: list[AgentDefinition] | None = None,
    ) -> CollaborationSession:
        """Start a multi-agent collaboration session.

        Default workflow:
        1. Architect designs approach
        2. Developer implements
        3. Reviewer checks
        4. Tester validates
        """
        session_id = str(uuid.uuid4())[:8]
        session_agents = agents or self.get_default_agents(
            AgentRole.ARCHITECT,
            AgentRole.DEVELOPER,
            AgentRole.REVIEWER,
        )

        session = CollaborationSession(
            id=session_id,
            task=task,
            agents=session_agents,
            status="active",
            created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

        self._sessions[session_id] = session
        self._message_queue[session_id] = []

        logger.info(
            "multi_agent.session_started",
            session_id=session_id,
            agents=len(session_agents),
            task=task[:200],
        )

        return session

    async def run_workflow(
        self,
        task: str,
        agents: list[AgentDefinition] | None = None,
    ) -> dict[str, Any]:
        """Run a complete multi-agent workflow.

        Sequential workflow:
        Each agent processes the task, and its output feeds into the next agent.
        """
        session = await self.start_collaboration(task, agents)
        results: dict[str, Any] = {}
        context = task

        for agent in session.agents:
            logger.info("multi_agent.agent_start", agent=agent.name, session=session.id)

            agent_result = await self._run_agent(agent, context, results)
            results[agent.role.value] = agent_result

            # Update context for next agent
            context = f"{context}\n\n{agent.name} output:\n{agent_result}"

        session.status = "completed"
        session.result = results
        session.completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")

        logger.info("multi_agent.workflow_complete", session_id=session.id)
        return results

    async def run_parallel_workflow(
        self,
        task: str,
        agents: list[AgentDefinition],
    ) -> dict[str, Any]:
        """Run agents in parallel on the same task and aggregate results."""
        import asyncio

        async def agent_task(agent: AgentDefinition) -> tuple[str, str]:
            result = await self._run_agent(agent, task, {})
            return agent.role.value, result

        tasks = [agent_task(a) for a in agents]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        results: dict[str, Any] = {}
        for item in results_list:
            if isinstance(item, Exception):
                logger.error("multi_agent.parallel_error", error=str(item))
            else:
                role, output = item
                results[role] = output

        return results

    # ── Agent Communication ─────────────────────────────────────

    async def send_message(self, session_id: str, message: AgentMessage) -> None:
        """Send a message between agents."""
        if session_id in self._message_queue:
            self._message_queue[session_id].append(message)
            logger.debug(
                "multi_agent.message",
                session=session_id,
                sender=message.sender,
                receiver=message.receiver,
            )

    async def get_messages(
        self,
        session_id: str,
        agent_name: str,
    ) -> list[AgentMessage]:
        """Get messages for a specific agent."""
        if session_id not in self._message_queue:
            return []
        return [
            m for m in self._message_queue[session_id]
            if m.receiver == agent_name or m.receiver == "all"
        ]

    # ── Helpers ─────────────────────────────────────────────────

    async def _run_agent(
        self,
        agent: AgentDefinition,
        task: str,
        previous_results: dict[str, Any],
    ) -> str:
        """Run a single agent on a task."""
        # Get provider
        provider_spec = self.registry.get_model_for_role(
            agent.model_preference or "reasoning"
        )
        if provider_spec:
            provider, model = provider_spec
        else:
            provider = self.registry.get(self.config.models.reasoning.provider)
            model = self.config.models.reasoning.model

        # Build prompt
        context_str = ""
        if previous_results:
            context_str = "\n\nPrevious results:\n"
            for role, result in previous_results.items():
                context_str += f"\n[{role}]: {result[:500]}"

        messages = [
            Message(role=MessageRole.SYSTEM, content=agent.system_prompt),
            Message(
                role=MessageRole.USER,
                content=f"Task: {task}\nYour role: {agent.role.value} ({agent.description})\n"
                        f"Capabilities: {', '.join(agent.capabilities)}{context_str}",
            ),
        ]

        request = CompletionRequest(
            messages=messages,
            model=model,
            temperature=0.1,
            max_tokens=2048,
        )

        response = await provider.complete(request)
        return response.content

    def get_session(self, session_id: str) -> CollaborationSession | None:
        """Get a collaboration session."""
        return self._sessions.get(session_id)

    def cleanup_session(self, session_id: str) -> None:
        """Clean up a completed session."""
        self._sessions.pop(session_id, None)
        self._message_queue.pop(session_id, None)
