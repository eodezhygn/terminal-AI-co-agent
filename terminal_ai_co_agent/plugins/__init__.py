"""Plugin subsystem — extensible plugin architecture."""

from terminal_ai_co_agent.plugins.manager import PluginManager
from terminal_ai_co_agent.plugins.types import (
    HookContext,
    HookPoint,
    Plugin,
    PluginMetadata,
    PluginStatus,
)

__all__ = [
    "PluginManager",
    "Plugin",
    "PluginMetadata",
    "PluginStatus",
    "HookPoint",
    "HookContext",
]
