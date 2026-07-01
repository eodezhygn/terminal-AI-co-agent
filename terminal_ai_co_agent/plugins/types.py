"""Type definitions for the plugin subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Protocol, runtime_checkable


class PluginStatus(str, Enum):
    """Lifecycle status of a plugin."""

    DISCOVERED = "discovered"
    LOADED = "loaded"
    INITIALIZED = "initialized"
    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"
    UNLOADED = "unloaded"


class HookPoint(str, Enum):
    """Points in the system where plugins can hook in."""

    # CLI hooks
    PRE_COMMAND = "pre_command"
    POST_COMMAND = "post_command"

    # Orchestration hooks
    PRE_PIPELINE = "pre_pipeline"
    POST_PIPELINE = "post_pipeline"
    PRE_STAGE = "pre_stage"
    POST_STAGE = "post_stage"

    # File operation hooks
    PRE_FILE_READ = "pre_file_read"
    POST_FILE_READ = "post_file_read"
    PRE_FILE_WRITE = "pre_file_write"
    POST_FILE_WRITE = "post_file_write"
    PRE_FILE_DELETE = "pre_file_delete"
    POST_FILE_DELETE = "post_file_delete"

    # Command hooks
    PRE_COMMAND_EXEC = "pre_command_exec"
    POST_COMMAND_EXEC = "post_command_exec"

    # Safety hooks
    PRE_SAFETY_CHECK = "pre_safety_check"
    POST_SAFETY_CHECK = "post_safety_check"

    # AI hooks
    PRE_COMPLETION = "pre_completion"
    POST_COMPLETION = "post_completion"

    # Context hooks
    PRE_CONTEXT_COLLECT = "pre_context_collect"
    POST_CONTEXT_COLLECT = "post_context_collect"

    # Custom
    CUSTOM = "custom"


@dataclass
class HookContext:
    """Context passed to hook handlers."""

    hook: HookPoint
    data: dict[str, Any] = field(default_factory=dict)
    plugin_name: str = ""
    timestamp: str = ""


@dataclass
class PluginMetadata:
    """Metadata describing a plugin."""

    name: str
    version: str
    description: str
    author: str = ""
    homepage: str = ""
    license: str = "MIT"
    dependencies: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    min_coagent_version: str = "0.1.0"


@runtime_checkable
class Plugin(Protocol):
    """Protocol that all plugins must implement."""

    @property
    def metadata(self) -> PluginMetadata:
        """Plugin metadata."""
        ...

    async def initialize(self) -> None:
        """Initialize the plugin. Called after loading."""
        ...

    async def shutdown(self) -> None:
        """Clean up plugin resources."""
        ...

    def get_hooks(self) -> dict[HookPoint, Callable[..., Any]]:
        """Return mapping of hook points to handler functions."""
        ...

    async def handle_hook(self, context: HookContext) -> HookContext:
        """Handle a hook invocation."""
        ...
