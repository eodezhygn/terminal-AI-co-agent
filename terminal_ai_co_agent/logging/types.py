"""Type definitions for the logging subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class LogLevel(str, Enum):
    """Log severity levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class AuditEntry:
    """A single audit trail entry."""

    timestamp: str
    event_type: str
    details: dict[str, Any] = field(default_factory=dict)
    session_id: str = ""
    request_id: str = ""


@dataclass
class MetricPoint:
    """A single metric data point."""

    name: str
    value: float
    timestamp: str
    tags: dict[str, str] = field(default_factory=dict)
    unit: str = ""
