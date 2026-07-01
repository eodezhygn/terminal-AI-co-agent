"""Execution sandboxing for unsafe or untrusted operations."""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from terminal_ai_co_agent.logging.logger import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class SandboxExecutor:
    """Execute commands in an isolated environment.

    Provides:
    - Temporary directory isolation
    - Environment variable filtering
    - Network restriction flags (honored by downstream)
    - Resource limits
    - Output capture

    Note: True OS-level sandboxing requires platform-specific
    support (Docker, bubblewrap, etc.). This class provides
    the interface and basic Python-level isolation.
    """

    def __init__(
        self,
        *,
        allow_network: bool = False,
        allow_fs_access: list[Path] | None = None,
        timeout: int = 300,
        max_output_bytes: int = 1_000_000,
    ) -> None:
        self.allow_network = allow_network
        self.allow_fs_access = allow_fs_access or []
        self.timeout = timeout
        self.max_output_bytes = max_output_bytes

    async def run(
        self,
        command: str,
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> tuple[int, str, str]:
        """Run a command in a temporary sandbox directory.

        Returns:
            Tuple of (return_code, stdout, stderr).
        """
        sandbox_dir = tempfile.mkdtemp(prefix="coagent_sandbox_")

        try:
            # Build minimal environment
            sandbox_env: dict[str, str] = {
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "HOME": sandbox_dir,
                "TMPDIR": sandbox_dir,
                "TEMP": sandbox_dir,
                "TMP": sandbox_dir,
            }

            if not self.allow_network:
                sandbox_env["http_proxy"] = ""
                sandbox_env["https_proxy"] = ""
                sandbox_env["HTTP_PROXY"] = ""
                sandbox_env["HTTPS_PROXY"] = ""
                sandbox_env["no_proxy"] = "*"

            if env:
                sandbox_env.update(env)

            process = await asyncio.create_subprocess_shell(
                command,
                cwd=cwd or sandbox_dir,
                env=sandbox_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=self.max_output_bytes,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return -1, "", f"Sandboxed command timed out after {self.timeout}s"

            stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
            stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""

            logger.debug("sandbox.complete", command=command[:100], return_code=process.returncode)

            return process.returncode or 0, stdout, stderr

        finally:
            # Cleanup sandbox directory
            import shutil
            try:
                shutil.rmtree(sandbox_dir, ignore_errors=True)
            except Exception:
                pass

    async def run_python(
        self,
        code: str,
        *,
        timeout: int = 30,
    ) -> tuple[int, str, str]:
        """Run Python code in a sandboxed subprocess."""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            prefix="coagent_sandbox_",
            delete=False,
        ) as f:
            f.write(code)
            script_path = f.name

        try:
            return await self.run(
                f"python {script_path}",
                timeout=timeout,
            )
        finally:
            try:
                os.unlink(script_path)
            except Exception:
                pass
