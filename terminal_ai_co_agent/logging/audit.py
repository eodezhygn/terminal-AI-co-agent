"""Audit trail logging for transparency and accountability."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from terminal_ai_co_agent.logging.logger import get_logger
from terminal_ai_co_agent.logging.types import AuditEntry

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

# Global session ID for audit correlation
_session_id: str = str(uuid.uuid4())[:8]
_audit_dir: Path | None = None
_audit_enabled: bool = True
_entries: list[AuditEntry] = []


def init_audit(
    audit_dir: Path | None = None,
    enabled: bool = True,
    session_id: str | None = None,
) -> None:
    """Initialize the audit subsystem.

    Args:
        audit_dir: Directory for audit log files.
        enabled: Whether audit logging is active.
        session_id: Custom session ID for correlation.
    """
    global _audit_dir, _audit_enabled, _session_id
    _audit_dir = audit_dir
    _audit_enabled = enabled
    if session_id:
        _session_id = session_id

    if audit_dir:
        audit_dir.mkdir(parents=True, exist_ok=True)

    logger.info("audit.initialized", session_id=_session_id, enabled=enabled)


def audit_event(
    event_type: str,
    **details: Any,
) -> None:
    """Record an audit event.

    Every significant action should emit an audit event:
    - File modifications
    - Command executions
    - AI completions
    - Configuration changes
    - Safety decisions
    - User approvals

    Args:
        event_type: Category of the event (e.g., "file_modified", "command_executed").
        **details: Arbitrary event data.
    """
    if not _audit_enabled:
        return

    entry = AuditEntry(
        timestamp=_now_iso(),
        event_type=event_type,
        details=details,
        session_id=_session_id,
        request_id=str(uuid.uuid4())[:8],
    )

    _entries.append(entry)
    logger.info(f"audit.{event_type}", **details)

    # Persist if directory configured
    if _audit_dir:
        _persist_entry(entry)


def get_audit_trail(
    event_type: str | None = None,
    limit: int = 100,
) -> list[AuditEntry]:
    """Retrieve recent audit entries, optionally filtered.

    Args:
        event_type: Filter by event type.
        limit: Maximum entries to return.

    Returns:
        List of audit entries (most recent last).
    """
    entries = _entries
    if event_type:
        entries = [e for e in entries if e.event_type == event_type]
    return entries[-limit:]


def clear_audit_trail() -> None:
    """Clear in-memory audit entries (does not delete persisted logs)."""
    _entries.clear()
    logger.debug("audit.cleared")


def _persist_entry(entry: AuditEntry) -> None:
    """Write an audit entry to disk."""
    if not _audit_dir:
        return

    audit_file = _audit_dir / f"audit-{_session_id}.jsonl"
    try:
        with open(audit_file, "a") as f:
            f.write(json.dumps({
                "timestamp": entry.timestamp,
                "event_type": entry.event_type,
                "session_id": entry.session_id,
                "request_id": entry.request_id,
                "details": entry.details,
            }) + "\n")
    except Exception as exc:
        logger.warning("audit.persist_error", error=str(exc))


def _now_iso() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
