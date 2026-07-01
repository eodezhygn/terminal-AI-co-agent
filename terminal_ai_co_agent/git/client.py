"""Git client abstraction with operation support."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from terminal_ai_co_agent.git.types import (
    GitBranch,
    GitCommit,
    GitDiff,
    GitFileStatus,
    GitOperation,
    GitStatus,
)
from terminal_ai_co_agent.logging.audit import audit_event
from terminal_ai_co_agent.logging.logger import get_logger

if TYPE_CHECKING:
    from terminal_ai_co_agent.config.types import GitConfig

logger = get_logger(__name__)


class GitClient:
    """Git client wrapping git commands with structured output.

    Provides:
    - Repository status
    - Diff generation
    - Branch management
    - Commit history
    - Safe operations with audit logging
    """

    def __init__(
        self,
        config: "GitConfig",
        project_root: Path | None = None,
    ) -> None:
        self.config = config
        self.project_root = project_root or Path.cwd()
        self._repo_root: Path | None = None

    # ── Repository Info ─────────────────────────────────────────

    async def _run_git(
        self,
        args: list[str],
        capture: bool = True,
        timeout: int = 30,
    ) -> tuple[int, str, str]:
        """Run a git command."""
        cmd = ["git"] + args
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=self.project_root,
            stdout=asyncio.subprocess.PIPE if capture else None,
            stderr=asyncio.subprocess.PIPE if capture else None,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return -1, "", "Git command timed out"

        return (
            process.returncode or 0,
            stdout.decode("utf-8", errors="replace") if stdout else "",
            stderr.decode("utf-8", errors="replace") if stderr else "",
        )

    async def is_repo(self) -> bool:
        """Check if the project root is a git repository."""
        returncode, _, _ = await self._run_git(["rev-parse", "--git-dir"])
        return returncode == 0

    async def get_repo_root(self) -> Path | None:
        """Get the root of the git repository."""
        if self._repo_root:
            return self._repo_root

        returncode, stdout, _ = await self._run_git(["rev-parse", "--show-toplevel"])
        if returncode == 0:
            self._repo_root = Path(stdout.strip())
            return self._repo_root
        return None

    # ── Status ──────────────────────────────────────────────────

    async def get_status(self) -> GitStatus:
        """Get the complete repository status."""
        # Branch info
        returncode, branch_name, _ = await self._run_git(
            ["rev-parse", "--abbrev-ref", "HEAD"]
        )
        branch = branch_name.strip() if returncode == 0 else "unknown"

        # Porcelain status
        returncode, porcelain, _ = await self._run_git(
            ["status", "--porcelain", "-b"]
        )
        if returncode != 0:
            return GitStatus(branch=branch, clean=True)

        lines = porcelain.splitlines()
        staged: list[GitFileStatus] = []
        unstaged: list[GitFileStatus] = []
        untracked: list[str] = []
        ahead = 0
        behind = 0

        for line in lines:
            if line.startswith("##"):
                # Branch line: "## main...origin/main [ahead 2, behind 1]"
                if "ahead" in line:
                    import re
                    ahead_match = re.search(r"ahead (\d+)", line)
                    behind_match = re.search(r"behind (\d+)", line)
                    if ahead_match:
                        ahead = int(ahead_match.group(1))
                    if behind_match:
                        behind = int(behind_match.group(1))
                continue

            if len(line) < 3:
                continue

            index_status = line[0]
            worktree_status = line[1]
            file_path = line[3:].strip()

            # Handle rename format: "R  old -> new"
            if index_status == "R" or worktree_status == "R":
                parts = file_path.split(" -> ")
                old_path = parts[0] if len(parts) > 1 else None
                file_path = parts[1] if len(parts) > 1 else file_path
            else:
                old_path = None

            if index_status != " ":
                staged.append(GitFileStatus(
                    path=file_path,
                    status=index_status,
                    staged=True,
                    old_path=old_path,
                ))

            if worktree_status != " ":
                if worktree_status == "?":
                    untracked.append(file_path)
                else:
                    unstaged.append(GitFileStatus(
                        path=file_path,
                        status=worktree_status,
                        staged=False,
                    ))

        # Stash count
        returncode, stash_output, _ = await self._run_git(["stash", "list"])
        stash_count = len(stash_output.splitlines()) if returncode == 0 and stash_output.strip() else 0

        return GitStatus(
            branch=branch,
            clean=not staged and not unstaged and not untracked,
            staged=staged,
            unstaged=unstaged,
            untracked=untracked,
            ahead=ahead,
            behind=behind,
            stash_count=stash_count,
        )

    # ── Diff ────────────────────────────────────────────────────

    async def get_diff(
        self,
        staged: bool = False,
        file_path: str | None = None,
    ) -> GitDiff | None:
        """Get the current diff."""
        args = ["diff"]
        if staged:
            args.append("--staged")
        if file_path:
            args.extend(["--", file_path])

        returncode, stdout, _ = await self._run_git(args)
        if returncode != 0 or not stdout.strip():
            return None

        diff_text = stdout
        lines = diff_text.splitlines()
        added = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))

        return GitDiff(
            file_path=file_path or "working_tree",
            diff_text=diff_text,
            lines_added=added,
            lines_removed=removed,
        )

    async def get_diff_between(
        self,
        ref1: str,
        ref2: str = "HEAD",
    ) -> list[GitDiff]:
        """Get diff between two refs."""
        returncode, stdout, _ = await self._run_git(
            ["diff", "--name-status", f"{ref1}..{ref2}"]
        )
        if returncode != 0:
            return []

        diffs: list[GitDiff] = []
        for line in stdout.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                file_path = parts[-1]
                diff = await self.get_diff(file_path=file_path)
                if diff:
                    diffs.append(diff)

        return diffs

    # ── Commits ─────────────────────────────────────────────────

    async def commit(
        self,
        message: str,
        files: list[str] | None = None,
        all_changes: bool = False,
    ) -> bool:
        """Create a commit."""
        # Stage files
        if files:
            await self._run_git(["add", "--"] + files)
        elif all_changes:
            await self._run_git(["add", "-A"])

        # Create commit
        if self.config.sign_commits:
            returncode, _, stderr = await self._run_git(
                ["commit", "-S", "-m", message]
            )
        else:
            returncode, _, stderr = await self._run_git(
                ["commit", "-m", message]
            )

        if returncode == 0:
            audit_event("git_commit", message=message, files=files)
            logger.info("git.committed", message=message[:100])
            return True

        logger.warning("git.commit_failed", error=stderr.strip())
        return False

    async def get_history(
        self,
        max_count: int = 20,
        file_path: str | None = None,
    ) -> list[GitCommit]:
        """Get commit history."""
        args = [
            "log",
            f"--max-count={max_count}",
            "--pretty=format:%H|%an|%ad|%s",
            "--date=short",
        ]
        if file_path:
            args.extend(["--", file_path])

        returncode, stdout, _ = await self._run_git(args)
        if returncode != 0:
            return []

        commits: list[GitCommit] = []
        for line in stdout.splitlines():
            parts = line.split("|", 3)
            if len(parts) >= 4:
                # Get stats for this commit
                stat_return, stat_out, _ = await self._run_git(
                    ["show", "--stat", "--format=", parts[0]]
                )
                files_changed = 0
                insertions = 0
                deletions = 0
                if stat_return == 0:
                    import re
                    last_line = stat_out.strip().split("\n")[-1] if stat_out.strip() else ""
                    match = re.search(
                        r"(\d+)\s+files?\s+changed.*?(\d+)\s+insertions?.*?(\d+)\s+deletions?",
                        last_line,
                    )
                    if match:
                        files_changed = int(match.group(1))
                        insertions = int(match.group(2))
                        deletions = int(match.group(3))

                commits.append(GitCommit(
                    hash=parts[0],
                    author=parts[1],
                    date=parts[2],
                    message=parts[3],
                    files_changed=files_changed,
                    insertions=insertions,
                    deletions=deletions,
                ))

        return commits

    # ── Branches ────────────────────────────────────────────────

    async def create_branch(self, name: str, switch: bool = True) -> bool:
        """Create a new branch."""
        args = ["checkout", "-b", name] if switch else ["branch", name]
        returncode, _, stderr = await self._run_git(args)

        if returncode == 0:
            logger.info("git.branch_created", name=name)
            audit_event("git_branch_created", branch=name)
            return True

        logger.warning("git.branch_failed", name=name, error=stderr.strip())
        return False

    async def switch_branch(self, name: str) -> bool:
        """Switch to an existing branch."""
        returncode, _, stderr = await self._run_git(["checkout", name])
        return returncode == 0

    async def get_branches(self) -> list[GitBranch]:
        """List all branches."""
        returncode, stdout, _ = await self._run_git(
            ["branch", "-a", "--format=%(refname:short)|%(HEAD)|%(upstream:short)|%(upstream:track)"]
        )
        if returncode != 0:
            return []

        branches: list[GitBranch] = []
        for line in stdout.splitlines():
            parts = line.split("|")
            if len(parts) >= 1:
                name = parts[0]
                is_current = len(parts) > 1 and parts[1] == "*"
                upstream = parts[2] if len(parts) > 2 and parts[2] else None
                track_info = parts[3] if len(parts) > 3 else ""

                ahead = 0
                behind = 0
                import re
                ahead_match = re.search(r"ahead (\d+)", track_info)
                behind_match = re.search(r"behind (\d+)", track_info)
                if ahead_match:
                    ahead = int(ahead_match.group(1))
                if behind_match:
                    behind = int(behind_match.group(1))

                branches.append(GitBranch(
                    name=name.replace("remotes/", ""),
                    is_current=is_current,
                    is_remote=name.startswith("remotes/"),
                    upstream=upstream,
                    ahead=ahead,
                    behind=behind,
                ))

        return branches

    async def get_current_branch(self) -> str:
        """Get current branch name."""
        returncode, stdout, _ = await self._run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        return stdout.strip() if returncode == 0 else "unknown"

    # ── Stash ───────────────────────────────────────────────────

    async def stash(self, message: str = "") -> bool:
        """Stash current changes."""
        args = ["stash", "push"]
        if message:
            args.extend(["-m", message])
        returncode, _, _ = await self._run_git(args)
        return returncode == 0

    async def stash_pop(self) -> bool:
        """Pop the most recent stash."""
        returncode, _, _ = await self._run_git(["stash", "pop"])
        return returncode == 0

    # ── Utility ─────────────────────────────────────────────────

    async def generate_branch_name(self, task_slug: str) -> str:
        """Generate a branch name from the config pattern."""
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        return self.config.branch_pattern.format(
            task_slug=task_slug[:30].replace(" ", "-").lower(),
            timestamp=timestamp,
        )

    async def ensure_safe_state(self) -> bool:
        """Check if repository is in a safe state for automated changes."""
        status = await self.get_status()

        if not status.clean and self.config.auto_commit:
            # Auto-commit changes
            branch_name = await self.generate_branch_name("auto-save")
            await self.create_branch(branch_name)
            await self.commit("Auto-save before coagent operation", all_changes=True)
            return True

        if status.ahead > 0 or status.behind > 0:
            logger.warning(
                "git.diverged",
                branch=status.branch,
                ahead=status.ahead,
                behind=status.behind,
            )

        return status.clean
