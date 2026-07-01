"""Hook system for plugin integration."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Callable

from terminal_ai_co_agent.logging.logger import get_logger
from terminal_ai_co_agent.plugins.types import HookContext, HookPoint

if TYPE_CHECKING:
    from terminal_ai_co_agent.plugins.loader import PluginLoader

logger = get_logger(__name__)


class HookManager:
    """Manages hook registration and dispatching.

    Hooks allow plugins to intercept and modify system behavior
    at well-defined points without modifying core code.
    """

    def __init__(self, plugin_loader: "PluginLoader") -> None:
        self.loader = plugin_loader
        self._handlers: dict[HookPoint, list[tuple[str, Callable[..., Any]]]] = {
            hook: [] for hook in HookPoint
        }

    # ── Registration ────────────────────────────────────────────

    async def register_plugin_hooks(self, plugin_name: str) -> None:
        """Register all hooks for a loaded plugin."""
        plugin = self.loader.get(plugin_name)
        if plugin is None:
            logger.warning("hooks.plugin_not_loaded", name=plugin_name)
            return

        hooks = plugin.get_hooks()
        for hook_point, handler in hooks.items():
            self._handlers[hook_point].append((plugin_name, handler))
            logger.debug(
                "hooks.registered",
                plugin=plugin_name,
                hook=hook_point.value,
            )

    def unregister_plugin_hooks(self, plugin_name: str) -> None:
        """Unregister all hooks for a plugin."""
        for hook_point in self._handlers:
            self._handlers[hook_point] = [
                (name, handler)
                for name, handler in self._handlers[hook_point]
                if name != plugin_name
            ]
        logger.debug("hooks.unregistered", plugin=plugin_name)

    async def register_all(self) -> None:
        """Register hooks for all loaded plugins."""
        for name in self.loader.get_all():
            await self.register_plugin_hooks(name)
        logger.info("hooks.registered_all", plugins=self.loader.loaded_count)

    # ── Dispatching ─────────────────────────────────────────────

    async def dispatch(
        self,
        hook_point: HookPoint,
        context: dict[str, Any] | None = None,
    ) -> HookContext:
        """Dispatch a hook to all registered handlers.

        Handlers are called in registration order.
        Each handler receives the context and can modify it.
        The modified context is passed to the next handler.

        Args:
            hook_point: Which hook to dispatch.
            context: Initial context data.

        Returns:
            Final HookContext after all handlers have run.
        """
        hook_context = HookContext(
            hook=hook_point,
            data=context or {},
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

        handlers = self._handlers.get(hook_point, [])
        if not handlers:
            return hook_context

        logger.debug(
            "hooks.dispatch",
            hook=hook_point.value,
            handlers=len(handlers),
        )

        for plugin_name, handler in handlers:
            hook_context.plugin_name = plugin_name
            try:
                result = handler(hook_context)
                if result is not None:
                    hook_context = result
            except Exception as exc:
                logger.error(
                    "hooks.handler_error",
                    plugin=plugin_name,
                    hook=hook_point.value,
                    error=str(exc),
                )
                # Continue with next handler despite error

        return hook_context

    async def dispatch_chain(
        self,
        hook_points: list[HookPoint],
        context: dict[str, Any] | None = None,
    ) -> HookContext:
        """Dispatch through a chain of hooks in sequence."""
        current_context = context or {}
        hook_context = HookContext(
            hook=HookPoint.CUSTOM,
            data=current_context,
        )

        for hook_point in hook_points:
            hook_context = await self.dispatch(hook_point, hook_context.data)

        return hook_context

    # ── Pre/Post Convenience ────────────────────────────────────

    async def pre_command(self, command_name: str, args: dict[str, Any]) -> HookContext:
        """Dispatch pre-command hook."""
        return await self.dispatch(
            HookPoint.PRE_COMMAND,
            {"command": command_name, "args": args},
        )

    async def post_command(
        self,
        command_name: str,
        result: Any,
        error: str | None = None,
    ) -> HookContext:
        """Dispatch post-command hook."""
        return await self.dispatch(
            HookPoint.POST_COMMAND,
            {"command": command_name, "result": result, "error": error},
        )

    async def pre_file_write(self, path: str, content_size: int) -> HookContext:
        """Dispatch pre-file-write hook."""
        return await self.dispatch(
            HookPoint.PRE_FILE_WRITE,
            {"path": path, "content_size": content_size},
        )

    async def post_file_write(self, path: str, success: bool, error: str = "") -> HookContext:
        """Dispatch post-file-write hook."""
        return await self.dispatch(
            HookPoint.POST_FILE_WRITE,
            {"path": path, "success": success, "error": error},
        )

    async def pre_completion(self, model: str, messages_count: int) -> HookContext:
        """Dispatch pre-completion hook."""
        return await self.dispatch(
            HookPoint.PRE_COMPLETION,
            {"model": model, "messages_count": messages_count},
        )

    async def post_completion(
        self,
        model: str,
        tokens: int,
        duration_ms: int,
    ) -> HookContext:
        """Dispatch post-completion hook."""
        return await self.dispatch(
            HookPoint.POST_COMPLETION,
            {"model": model, "tokens": tokens, "duration_ms": duration_ms},
        )

    # ── Query ───────────────────────────────────────────────────

    def get_handler_count(self, hook_point: HookPoint | None = None) -> int:
        """Get the number of registered handlers."""
        if hook_point:
            return len(self._handlers.get(hook_point, []))
        return sum(len(handlers) for handlers in self._handlers.values())

    def list_hooks(self) -> dict[str, list[str]]:
        """List all hooks and their registered plugins."""
        return {
            hook.value: [name for name, _ in handlers]
            for hook, handlers in self._handlers.items()
            if handlers
        }
