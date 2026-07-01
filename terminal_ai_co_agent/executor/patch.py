"""Patch generation, validation, and application."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from unidiff import PatchSet

from terminal_ai_co_agent.executor.types import (
    OperationResult,
    OperationStatus,
    OperationType,
)
from terminal_ai_co_agent.logging.audit import audit_event
from terminal_ai_co_agent.logging.logger import get_logger

if TYPE_CHECKING:
    from terminal_ai_co_agent.executor.file_ops import FileOperator

logger = get_logger(__name__)


class PatchEngine:
    """Unified diff patch generation and application.

    Works with the FileOperator for safe application with rollback.
    """

    def __init__(self, file_operator: FileOperator) -> None:
        self.file_ops = file_operator

    # ── Generation ───────────────────────────────────────────────

    def generate_diff(
        self,
        original: str,
        modified: str,
        file_path: str = "file",
    ) -> str:
        """Generate a unified diff between original and modified content."""
        import difflib

        original_lines = original.splitlines(keepends=True)
        modified_lines = modified.splitlines(keepends=True)

        diff = difflib.unified_diff(
            original_lines,
            modified_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
        )
        return "".join(diff)

    def generate_project_diff(
        self,
        changes: dict[Path, str],
    ) -> str:
        """Generate a combined diff for multiple file changes."""
        diffs = []
        for path, new_content in changes.items():
            original_content = ""
            if path.exists():
                original_content = path.read_text()
            diff = self.generate_diff(original_content, new_content, str(path))
            if diff:
                diffs.append(diff)
        return "\n".join(diffs)

    # ── Validation ───────────────────────────────────────────────

    def validate_patch(self, patch_text: str) -> tuple[bool, str]:
        """Validate that a patch can be parsed.

        Returns:
            Tuple of (is_valid, error_message).
        """
        if not patch_text.strip():
            return False, "Patch is empty"

        try:
            patch_set = PatchSet.from_string(patch_text)
            if len(patch_set) == 0:
                return False, "Patch contains no file changes"
            return True, f"Valid patch with {len(patch_set)} file(s)"
        except Exception as exc:
            return False, f"Invalid patch format: {exc}"

    # ── Application ──────────────────────────────────────────────

    async def apply_patch(
        self,
        patch_text: str,
        *,
        base_dir: Path | None = None,
    ) -> list[OperationResult]:
        """Apply a unified diff patch to the project.

        Each file modification goes through the FileOperator for safety.
        """
        patch_set = PatchSet.from_string(patch_text)
        base = base_dir or Path.cwd()
        results: list[OperationResult] = []
        patch_id = self._make_id()

        logger.info("patch.apply", files=len(patch_set), patch_id=patch_id)
        audit_event("patch_apply_start", patch_id=patch_id, files=len(patch_set))

        for patched_file in patch_set:
            target_path = (base / patched_file.path).resolve()

            if patched_file.is_added_file:
                # New file
                content = str(patched_file)
                result = await self.file_ops.write(target_path, content)
                result.operation_id = f"{patch_id}:{target_path.name}"
                results.append(result)

            elif patched_file.is_removed_file:
                # Deleted file
                result = await self.file_ops.delete(target_path)
                result.operation_id = f"{patch_id}:{target_path.name}"
                results.append(result)

            else:
                # Modified file
                try:
                    original = target_path.read_text()
                    modified = str(patched_file)

                    # Apply hunk by hunk validation
                    for hunk in patched_file:
                        pass  # Hunk-level validation could go here

                    result = await self.file_ops.write(target_path, modified)
                    result.metadata["patch_hunks"] = len(patched_file)
                    result.operation_id = f"{patch_id}:{target_path.name}"
                    results.append(result)

                except FileNotFoundError:
                    results.append(
                        OperationResult(
                            success=False,
                            operation_id=f"{patch_id}:{target_path.name}",
                            status=OperationStatus.FAILED,
                            error=f"Target file not found: {target_path}",
                        )
                    )
                except Exception as exc:
                    logger.error("patch.hunk_error", file=str(target_path), error=str(exc))
                    results.append(
                        OperationResult(
                            success=False,
                            operation_id=f"{patch_id}:{target_path.name}",
                            status=OperationStatus.FAILED,
                            error=str(exc),
                        )
                    )

        all_success = all(r.success for r in results)
        audit_event(
            "patch_apply_complete",
            patch_id=patch_id,
            success=all_success,
            results=len(results),
        )

        return results

    async def apply_single_file_change(
        self,
        path: Path,
        new_content: str,
    ) -> OperationResult:
        """Apply a change to a single file, generating a diff internally."""
        original_content = ""
        if path.exists():
            read_result = await self.file_ops.read(path)
            if read_result.success:
                original_content = read_result.output

        diff = self.generate_diff(original_content, new_content, str(path))
        logger.debug("patch.single_file", path=str(path), diff_size=len(diff))

        result = await self.file_ops.write(path, new_content)
        result.metadata["diff"] = diff
        return result

    # ── Helpers ──────────────────────────────────────────────────

    def _make_id(self) -> str:
        return uuid.uuid4().hex[:12]
