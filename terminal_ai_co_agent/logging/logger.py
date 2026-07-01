"""Structured logging setup using structlog."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from structlog.types import Processor

from terminal_ai_co_agent.logging.types import LogLevel

if TYPE_CHECKING:
    pass


def configure_logging(
    level: LogLevel = LogLevel.INFO,
    json_format: bool = False,
    log_directory: Path | None = None,
) -> None:
    """Configure structured logging for the entire application.

    Args:
        level: Minimum log level to emit.
        json_format: If True, emit JSON lines (for production/ingestion).
                     If False, emit colored console output (for development).
        log_directory: If set, also write logs to this directory.
    """
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if json_format:
        # Machine-readable JSON output
        structlog.configure(
            processors=[
                *shared_processors,
                structlog.processors.dict_tracebacks,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(
                getattr(structlog, level.value, 20)
            ),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(sys.stderr),
            cache_logger_on_first_use=True,
        )
    else:
        # Human-readable console output
        structlog.configure(
            processors=[
                *shared_processors,
                structlog.dev.ConsoleRenderer(colors=True),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(
                getattr(structlog, level.value, 20)
            ),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(sys.stderr),
            cache_logger_on_first_use=True,
        )

    # File output if requested
    if log_directory is not None:
        _add_file_output(log_directory, json_format)


def _add_file_output(log_directory: Path, json_format: bool) -> None:
    """Add file-based logging handler."""
    # File logging is handled via standard logging integration
    # when persistence beyond console is needed
    import logging
    from logging.handlers import RotatingFileHandler

    log_directory.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(
        log_directory / "coagent.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
    )

    if json_format:
        file_handler.setFormatter(
            logging.Formatter('{"timestamp":"%(asctime)s","level":"%(levelname)s","message":%(message)s}')
        )
    else:
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        )

    root_logger = logging.getLogger("terminal_ai_co_agent")
    root_logger.addHandler(file_handler)


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    """Get a structured logger instance.

    Usage:
        logger = get_logger(__name__)
        logger.info("event.name", key="value", another_key=123)
    """
    return structlog.get_logger(name or "terminal_ai_co_agent")
