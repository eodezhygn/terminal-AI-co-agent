"""Deployment engine — coordinates deployment to various targets."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from terminal_ai_co_agent.deployment.types import (
    DeploymentConfig,
    DeploymentResult,
    DeploymentStatus,
    DeploymentTarget,
)
from terminal_ai_co_agent.executor.command_ops import CommandExecutor
from terminal_ai_co_agent.executor.types import CommandOperation
from terminal_ai_co_agent.logging.logger import get_logger

if TYPE_CHECKING:
    from terminal_ai_co_agent.config.types import CoAgentConfig

logger = get_logger(__name__)


class DeploymentEngine:
    """Coordinates application deployment.

    Supports:
    - Docker container builds and pushes
    - Cloud Run deployments
    - Kubernetes manifests
    - Local deployment scripts
    - Custom deployment commands

    Note: This is an interface layer. Actual deployment relies on
    platform-specific tools (docker, kubectl, gcloud, etc.) being installed.
    """

    def __init__(self, config: "CoAgentConfig") -> None:
        self.config = config
        self.command_executor = CommandExecutor(config)

    async def deploy(self, deploy_config: DeploymentConfig) -> DeploymentResult:
        """Execute a deployment."""
        logger.info(
            "deployment.starting",
            target=deploy_config.target.value,
            project=deploy_config.project_name,
            environment=deploy_config.environment,
        )

        if deploy_config.target == DeploymentTarget.DOCKER:
            return await self._deploy_docker(deploy_config)
        elif deploy_config.target == DeploymentTarget.KUBERNETES:
            return await self._deploy_kubernetes(deploy_config)
        elif deploy_config.target == DeploymentTarget.LOCAL:
            return await self._deploy_local(deploy_config)
        else:
            return DeploymentResult(
                success=False,
                status=DeploymentStatus.FAILED,
                target=deploy_config.target,
                message=f"Deployment target '{deploy_config.target.value}' not yet implemented",
            )

    async def _deploy_docker(self, config: DeploymentConfig) -> DeploymentResult:
        """Build and deploy a Docker container."""
        import time
        start = time.monotonic()

        # Build image
        build_cmd = config.build_command or f"docker build -t {config.project_name}:latest ."
        result = await self.command_executor.run(CommandOperation(command=build_cmd))

        if not result.success:
            return DeploymentResult(
                success=False,
                status=DeploymentStatus.FAILED,
                target=DeploymentTarget.DOCKER,
                message=f"Docker build failed: {result.error}",
                logs=result.output,
            )

        # Push image (if registry configured)
        if config.resources.get("registry"):
            registry = config.resources["registry"]
            tag_cmd = f"docker tag {config.project_name}:latest {registry}/{config.project_name}:latest"
            await self.command_executor.run(CommandOperation(command=tag_cmd))

            push_cmd = f"docker push {registry}/{config.project_name}:latest"
            push_result = await self.command_executor.run(CommandOperation(command=push_cmd))

            if not push_result.success:
                return DeploymentResult(
                    success=False,
                    status=DeploymentStatus.FAILED,
                    target=DeploymentTarget.DOCKER,
                    message=f"Docker push failed: {push_result.error}",
                    logs=push_result.output,
                )

        elapsed = int((time.monotonic() - start) * 1000)

        return DeploymentResult(
            success=True,
            status=DeploymentStatus.SUCCEEDED,
            target=DeploymentTarget.DOCKER,
            message="Docker image built and pushed successfully",
            duration_ms=elapsed,
            metadata={"image": f"{config.project_name}:latest"},
        )

    async def _deploy_kubernetes(self, config: DeploymentConfig) -> DeploymentResult:
        """Deploy to Kubernetes."""
        import time
        start = time.monotonic()

        # Apply manifests
        manifest_path = config.resources.get("manifest_path", "k8s/")
        apply_cmd = f"kubectl apply -f {manifest_path}"

        if config.environment != "production":
            apply_cmd += f" -n {config.environment}"

        result = await self.command_executor.run(CommandOperation(command=apply_cmd))

        elapsed = int((time.monotonic() - start) * 1000)

        return DeploymentResult(
            success=result.success,
            status=DeploymentStatus.SUCCEEDED if result.success else DeploymentStatus.FAILED,
            target=DeploymentTarget.KUBERNETES,
            message="Kubernetes deployment " + ("succeeded" if result.success else "failed"),
            logs=result.output,
            duration_ms=elapsed,
        )

    async def _deploy_local(self, config: DeploymentConfig) -> DeploymentResult:
        """Run deployment locally."""
        import time
        start = time.monotonic()

        cmd = config.start_command or config.build_command or "echo 'No deployment command configured'"
        result = await self.command_executor.run(CommandOperation(command=cmd))

        elapsed = int((time.monotonic() - start) * 1000)

        return DeploymentResult(
            success=result.success,
            status=DeploymentStatus.SUCCEEDED if result.success else DeploymentStatus.FAILED,
            target=DeploymentTarget.LOCAL,
            message="Local deployment " + ("completed" if result.success else "failed"),
            logs=result.output,
            duration_ms=elapsed,
        )

    async def rollback(self, config: DeploymentConfig) -> DeploymentResult:
        """Rollback a deployment."""
        logger.info("deployment.rollback", target=config.target.value)

        if config.target == DeploymentTarget.KUBERNETES:
            cmd = f"kubectl rollout undo deployment/{config.project_name}"
            if config.environment != "production":
                cmd += f" -n {config.environment}"
            result = await self.command_executor.run(CommandOperation(command=cmd))

            return DeploymentResult(
                success=result.success,
                status=DeploymentStatus.ROLLED_BACK if result.success else DeploymentStatus.FAILED,
                target=config.target,
                message="Rollback " + ("succeeded" if result.success else "failed"),
                logs=result.output,
            )

        return DeploymentResult(
            success=False,
            status=DeploymentStatus.FAILED,
            target=config.target,
            message=f"Rollback not supported for {config.target.value}",
        )
