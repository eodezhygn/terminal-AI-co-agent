"""Type definitions for the multi-agent subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentRole(str, Enum):
    """Roles an agent can play in multi-agent collaboration."""

    COORDINATOR = "coordinator"
    DEVELOPER = "developer"
    REVIEWER = "reviewer"
    TESTER = "tester"
    DOCUMENTER = "documenter"
    SECURITY_AUDITOR = "security_auditor"
    ARCHITECT = "architect"
    DEVOPS = "devops"
    CUSTOM = "custom"


class AgentStatus(str, Enum):
    """Status of an agent."""

    IDLE = "idle"
    WORKING = "working"
    WAITING = "waiting"
    DONE = "done"
    ERROR = "error"


@dataclass
class AgentMessage:
    """A message between agents."""

    id: str
    sender: str
    receiver: str
    content: str
    message_type: str = "task"  # task, response, question, feedback
    priority: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""


@dataclass
class AgentDefinition:
    """Definition of an agent."""

    name: str
    role: AgentRole
    description: str
    capabilities: list[str] = field(default_factory=list)
    model_preference: str = "reasoning"  # Which model to use
    system_prompt: str = ""
    max_concurrent_tasks: int = 1


@dataclass
class CollaborationSession:
    """A multi-agent collaboration session."""

    id: str
    task: str
    agents: list[AgentDefinition]
    messages: list[AgentMessage] = field(default_factory=list)
    status: str = "initializing"
    result: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    completed_at: str = ""
