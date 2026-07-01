"""AI provider registry for dynamic provider management."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from terminal_ai_co_agent.ai.types import AIProvider, ModelInfo, ModelRole
from terminal_ai_co_agent.logging.logger import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class ProviderRegistry:
    """Registry for managing multiple AI providers.

    Supports:
    - Provider registration/unregistration
    - Model discovery across all providers
    - Provider selection by model name
    - Model role assignment
    """

    def __init__(self) -> None:
        self._providers: dict[str, AIProvider] = {}
        self._role_assignments: dict[ModelRole, str] = {}

    # ── Registration ────────────────────────────────────────────

    def register(self, provider: AIProvider) -> None:
        """Register an AI provider."""
        name = provider.provider_name
        if name in self._providers:
            logger.warning(
                "provider.overwrite",
                provider=name,
                message="Replacing existing provider",
            )
        self._providers[name] = provider
        logger.info("provider.registered", provider=name)

    def unregister(self, provider_name: str) -> None:
        """Remove a registered provider."""
        if provider_name in self._providers:
            del self._providers[provider_name]
            # Clean up role assignments
            self._role_assignments = {
                role: p
                for role, p in self._role_assignments.items()
                if p != provider_name
            }
            logger.info("provider.unregistered", provider=provider_name)

    def get(self, provider_name: str) -> AIProvider:
        """Get a provider by name."""
        try:
            return self._providers[provider_name]
        except KeyError:
            raise ProviderNotFoundError(
                f"Provider '{provider_name}' not found. "
                f"Available: {list(self._providers.keys())}"
            )

    # ── Model Discovery ─────────────────────────────────────────

    async def discover_models(self) -> dict[str, list[ModelInfo]]:
        """Discover models from all registered providers."""
        results: dict[str, list[ModelInfo]] = {}
        for name, provider in self._providers.items():
            try:
                results[name] = await provider.available_models
            except Exception as exc:
                logger.warning(
                    "provider.discover.error",
                    provider=name,
                    error=str(exc),
                )
                results[name] = []
        return results

    async def find_model(self, model_name: str) -> tuple[AIProvider, ModelInfo] | None:
        """Find a model across all providers."""
        for provider in self._providers.values():
            for model in await provider.available_models:
                if model.name == model_name:
                    return provider, model
        return None

    # ── Role Assignment ─────────────────────────────────────────

    def assign_role(self, role: ModelRole, provider_name: str, model_name: str) -> None:
        """Assign a specific model+provider to a role."""
        if provider_name not in self._providers:
            raise ProviderNotFoundError(f"Provider '{provider_name}' not registered")
        self._role_assignments[role] = f"{provider_name}:{model_name}"
        logger.info(
            "role.assigned",
            role=role.value,
            provider=provider_name,
            model=model_name,
        )

    def get_model_for_role(self, role: ModelRole) -> tuple[AIProvider, str] | None:
        """Get the provider and model assigned to a role."""
        spec = self._role_assignments.get(role)
        if spec is None:
            return None
        provider_name, model_name = spec.split(":", 1)
        try:
            return self.get(provider_name), model_name
        except ProviderNotFoundError:
            return None

    # ── Health ──────────────────────────────────────────────────

    async def health_check_all(self) -> dict[str, Any]:
        """Check health of all providers."""
        results: dict[str, Any] = {}
        for name, provider in self._providers.items():
            try:
                results[name] = await provider.verify_capability()
            except Exception as exc:
                results[name] = {"healthy": False, "error": str(exc)}
        return results

    @property
    def provider_names(self) -> list[str]:
        """List registered provider names."""
        return list(self._providers.keys())

    @property
    def active_providers(self) -> dict[str, AIProvider]:
        """Return all registered providers."""
        return dict(self._providers)


class ProviderNotFoundError(Exception):
    """Raised when a provider is not found."""
    pass
