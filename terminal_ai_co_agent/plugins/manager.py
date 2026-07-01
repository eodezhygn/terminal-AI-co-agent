"""Plugin lifecycle manager — coordinates loading, hooks, and configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from terminal_ai_co_agent.logging.logger import get_logger
from terminal_ai_co_agent.plugins.hooks import HookManager
from terminal_ai_co_agent.plugins.loader import PluginLoader
from terminal_ai_co_agent.plugins.types import Plugin, PluginStatus

if TYPE_CHECKING:
    from terminal_ai_co_agent.config.types import PluginsConfig

logger = get_logger(__name__)


class PluginManager:
    """Central plugin management.

    Coordinates:
    - Plugin discovery
    - Loading and initialization
    - Hook registration
    - Lifecycle management
    - Status tracking
    """

    def __init__(self, config: "PluginsConfig") -> None:
        self.config = config
        self.loader = PluginLoader(config)
        self.hooks = HookManager(self.loader)
        self._initialized = False

    # ── Lifecycle ───────────────────────────────────────────────

    async def initialize(self) -> None:
        """Initialize the plugin system.

        Discovers plugins, loads enabled ones, and registers hooks.
        """
        if self._initialized:
            return

        if not self.config.enabled:
            logger.info("plugins.system_disabled")
            return

        # Discover
        await self.loader.discover_all()

        # Load enabled plugins
        await self.loader.load_all()

        # Register hooks
        await self.hooks.register_all()

        self._initialized = True
        logger.info(
            "plugins.initialized",
            loaded=self.loader.loaded_count,
            hooks=self.hooks.get_handler_count(),
        )

    async def shutdown(self) -> None:
        """Shutdown the plugin system."""
        if not self._initialized:
            return

        await self.loader.unload_all()
        self._initialized = False
        logger.info("plugins.shutdown")

    # ── Plugin CRUD ─────────────────────────────────────────────

    async def load_plugin(self, name: str) -> Plugin:
        """Load and activate a specific plugin."""
        plugin = await self.loader.load(name)
        await self.hooks.register_plugin_hooks(name)
        return plugin

    async def unload_plugin(self, name: str) -> None:
        """Unload a plugin and its hooks."""
        self.hooks.unregister_plugin_hooks(name)
        await self.loader.unload(name)

    async def enable_plugin(self, name: str) -> None:
        """Enable a disabled plugin."""
        await self.loader.enable(name)
        await self.hooks.register_plugin_hooks(name)

    async def disable_plugin(self, name: str) -> None:
        """Disable an active plugin."""
        self.hooks.unregister_plugin_hooks(name)
        await self.loader.disable(name)

    # ── Status ──────────────────────────────────────────────────

    def get_status(self) -> list[dict[str, Any]]:
        """Get status of all plugins."""
        return self.loader.list_available()

    def get_plugin(self, name: str) -> Plugin | None:
        """Get a loaded plugin."""
        return self.loader.get(name)

    @property
    def active_plugins(self) -> dict[str, Plugin]:
        """Get all active plugins."""
        return self.loader.get_all()

    @property
    def is_enabled(self) -> bool:
        """Check if plugin system is enabled."""
        return self.config.enabled and self._initialized
