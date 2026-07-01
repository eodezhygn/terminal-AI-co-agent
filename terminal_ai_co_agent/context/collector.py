"""Context collection coordinator."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from terminal_ai_co_agent.context.extractors.source import SourceExtractor
from terminal_ai_co_agent.context.extractors.structure import StructureExtractor
from terminal_ai_co_agent.context.types import (
    ContextPackage,
    FileContext,
    ProjectContext,
)
from terminal_ai_co_agent.logging.audit import audit_event
from terminal_ai_co_agent.logging.logger import get_logger

if TYPE_CHECKING:
    from terminal_ai_co_agent.config.types import CoAgentConfig

logger = get_logger(__name__)


class ContextCollector:
    """Coordinates context extraction from multiple sources.

    Gathers:
    - Project structure
    - Source code (symbols, imports, structure)
    - Configuration files
    - Documentation
    - Dependencies
    - Git history
    - Test suites
    - PRDs / requirements

    Produces structured ProjectContext and compressed ContextPackages
    optimized for different model sizes.
    """

    def __init__(self, config: "CoAgentConfig") -> None:
        self.config = config
        self.project_root = Path(config.general.project_root).resolve()
        self.source_extractor = SourceExtractor(self.project_root)
        self.structure_extractor = StructureExtractor(self.project_root)
        self._cached_context: ProjectContext | None = None

    # ── Full Collection ─────────────────────────────────────────

    async def collect_full(self, *, force: bool = False) -> ProjectContext:
        """Collect complete project context.

        Args:
            force: If True, bypass cache and re-extract everything.

        Returns:
            Complete ProjectContext for the current project.
        """
        if self._cached_context and not force:
            logger.debug("context.cache_hit")
            return self._cached_context

        logger.info("context.collect_full.start", root=str(self.project_root))

        # Extract structure
        structure = self.structure_extractor.extract()

        # Extract source files
        source_files = self.source_extractor.extract_directory(self.project_root)

        # Detect project metadata
        name, description = self._detect_project_metadata()

        # Build context
        context = ProjectContext(
            project_root=self.project_root,
            name=name,
            description=description,
            language=structure["type"],
            framework=self._detect_framework(source_files),
            files=source_files,
            structure=structure,
            dependencies=self._extract_dependencies(),
            dev_dependencies=self._extract_dev_dependencies(),
            entry_points=structure["entry_points"],
            conventions=self._detect_conventions(source_files),
            git_info=self._collect_git_info(),
            test_framework=self._detect_test_framework(),
            build_system=structure["build_system"],
        )

        self._cached_context = context

        logger.info(
            "context.collect_full.complete",
            files=len(source_files),
            symbols=sum(len(f.symbols) for f in source_files),
        )

        audit_event(
            "context_collected",
            files=len(source_files),
            language=structure["type"],
        )

        return context

    async def collect_files(
        self,
        paths: list[Path],
    ) -> list[FileContext]:
        """Collect context for specific files only."""
        contexts: list[FileContext] = []
        for path in paths:
            full_path = (self.project_root / path).resolve()
            ctx = self.source_extractor.extract_file(full_path)
            if ctx:
                contexts.append(ctx)
        return contexts

    # ── Context Packaging ───────────────────────────────────────

    def package_for_model(
        self,
        context: ProjectContext,
        task: str,
        *,
        max_tokens: int = 4096,
    ) -> ContextPackage:
        """Package context into a compact form for model consumption.

        Prioritizes:
        1. Files relevant to the task
        2. Project structure overview
        3. Dependency information
        4. Coding conventions
        5. Recent changes
        """
        # Find relevant files based on task keywords
        relevant = self._find_relevant_files(context, task)

        # Build compressed package
        structure_overview = self.structure_extractor.get_tree(max_depth=2)

        # Estimate tokens (rough: 1 token ≈ 4 characters)
        total_chars = sum(len(f.raw_content) for f in relevant)
        total_chars += len(structure_overview) + 500  # overhead
        estimated_tokens = total_chars // 4

        compression_ratio = (
            1.0 - (estimated_tokens / max(estimated_tokens * 2, 1))
            if estimated_tokens > 0
            else 0.0
        )

        package = ContextPackage(
            project_summary=f"{context.name}: {context.description}",
            relevant_files=relevant,
            structure_overview=structure_overview,
            dependency_graph=self._build_dependency_graph(context),
            conventions=context.conventions,
            recent_changes=self._format_git_info(context.git_info),
            total_tokens=estimated_tokens,
            compression_ratio=compression_ratio,
            metadata={
                "language": context.language,
                "framework": context.framework,
                "test_framework": context.test_framework,
            },
        )

        logger.debug(
            "context.packaged",
            relevant_files=len(relevant),
            estimated_tokens=estimated_tokens,
        )

        return package

    # ── Cache Management ────────────────────────────────────────

    def invalidate_cache(self) -> None:
        """Invalidate the cached context."""
        self._cached_context = None
        logger.debug("context.cache_invalidated")

    def refresh(self) -> ProjectContext:
        """Force-refresh and return context."""
        return self.collect_full(force=True)

    # ── Detection Helpers ───────────────────────────────────────

    def _detect_project_metadata(self) -> tuple[str, str]:
        """Detect project name and description from config files."""
        name = self.project_root.name
        description = ""

        # Try pyproject.toml
        pyproject = self.project_root / "pyproject.toml"
        if pyproject.exists():
            try:
                import tomli
                with open(pyproject, "rb") as f:
                    data = tomli.load(f)
                project = data.get("project", {})
                name = project.get("name", name)
                description = project.get("description", "")
            except Exception:
                pass

        # Try package.json
        pkg_json = self.project_root / "package.json"
        if pkg_json.exists():
            try:
                import json
                with open(pkg_json) as f:
                    data = json.load(f)
                name = data.get("name", name)
                description = data.get("description", "")
            except Exception:
                pass

        return name, description

    def _detect_framework(self, files: list[FileContext]) -> str:
        """Detect web/application framework."""
        all_imports = []
        for f in files:
            all_imports.extend(f.imports)

        framework_indicators = {
            "fastapi": ["fastapi"],
            "flask": ["flask"],
            "django": ["django"],
            "react": ["react"],
            "next.js": ["next"],
            "vue": ["vue"],
            "angular": ["@angular/core"],
            "express": ["express"],
            "nestjs": ["@nestjs/core"],
        }

        for framework, indicators in framework_indicators.items():
            for indicator in indicators:
                if any(indicator in imp for imp in all_imports):
                    return framework

        return "none"

    def _extract_dependencies(self) -> dict[str, str]:
        """Extract production dependencies."""
        return self._parse_dependency_file("dependencies")

    def _extract_dev_dependencies(self) -> dict[str, str]:
        """Extract dev dependencies."""
        return self._parse_dependency_file("dev_dependencies")

    def _parse_dependency_file(self, dep_type: str) -> dict[str, str]:
        """Parse dependency files for version info."""
        deps: dict[str, str] = {}

        # pyproject.toml
        pyproject = self.project_root / "pyproject.toml"
        if pyproject.exists():
            try:
                import tomli
                with open(pyproject, "rb") as f:
                    data = tomli.load(f)
                project = data.get("project", {})
                target = project.get(dep_type, {})
                if isinstance(target, dict):
                    deps.update(target)
                elif isinstance(target, list):
                    for dep in target:
                        if isinstance(dep, str):
                            deps[dep] = "*"
            except Exception:
                pass

        return deps

    def _detect_conventions(self, files: list[FileContext]) -> dict[str, Any]:
        """Detect coding conventions from source files."""
        conventions: dict[str, Any] = {}

        python_files = [f for f in files if f.language == "python"]
        if python_files:
            # Detect quote style
            single_quotes = sum(1 for f in python_files if "'" in f.raw_content[:500])
            double_quotes = sum(1 for f in python_files if '"' in f.raw_content[:500])
            conventions["quote_style"] = "single" if single_quotes > double_quotes else "double"

            # Detect line length from first few files
            line_lengths = []
            for f in python_files[:10]:
                lines = f.raw_content.splitlines()
                line_lengths.extend(len(l) for l in lines if l.strip())
            if line_lengths:
                conventions["max_line_length"] = max(set(line_lengths), key=line_lengths.count)

            # Detect type hints usage
            has_type_hints = any(": " in f.raw_content and "def " in f.raw_content for f in python_files)
            conventions["type_hints"] = has_type_hints

        return conventions

    def _collect_git_info(self) -> dict[str, Any]:
        """Collect git repository information."""
        git_info: dict[str, Any] = {
            "has_git": False,
            "branch": "",
            "recent_commits": [],
            "remote": "",
        }

        git_dir = self.project_root / ".git"
        if not git_dir.exists():
            return git_info

        git_info["has_git"] = True

        try:
            import subprocess

            # Current branch
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                cwd=self.project_root,
                timeout=5,
            )
            if result.returncode == 0:
                git_info["branch"] = result.stdout.strip()

            # Recent commits
            result = subprocess.run(
                ["git", "log", "--oneline", "-10"],
                capture_output=True,
                text=True,
                cwd=self.project_root,
                timeout=5,
            )
            if result.returncode == 0:
                git_info["recent_commits"] = [
                    line.strip() for line in result.stdout.splitlines() if line.strip()
                ]

            # Remote
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                cwd=self.project_root,
                timeout=5,
            )
            if result.returncode == 0:
                git_info["remote"] = result.stdout.strip()

        except Exception as exc:
            logger.debug("context.git_error", error=str(exc))

        return git_info

    def _detect_test_framework(self) -> str:
        """Detect test framework from project dependencies."""
        test_indicators = {
            "pytest": ["pytest", "pytest.ini", "pyproject.toml"],
            "unittest": [],
            "jest": ["jest"],
            "vitest": ["vitest"],
            "mocha": ["mocha"],
            "go test": ["go.mod"],
            "cargo test": ["Cargo.toml"],
        }

        for framework, indicators in test_indicators.items():
            if not indicators:
                continue
            for indicator in indicators:
                if (self.project_root / indicator).exists():
                    return framework

        return "unknown"

    def _find_relevant_files(
        self,
        context: ProjectContext,
        task: str,
        max_files: int = 20,
    ) -> list[FileContext]:
        """Find files most relevant to a given task."""
        task_lower = task.lower()
        keywords = task_lower.split()

        scored_files: list[tuple[float, FileContext]] = []

        for file_ctx in context.files:
            score = 0.0
            file_name_lower = file_ctx.path.name.lower()

            # File name matches
            for kw in keywords:
                if kw in file_name_lower:
                    score += 2.0

            # Symbol matches
            for symbol in file_ctx.symbols:
                for kw in keywords:
                    if kw in symbol.name.lower():
                        score += 3.0

            # Import matches
            for imp in file_ctx.imports:
                for kw in keywords:
                    if kw in imp.lower():
                        score += 1.5

            # Content match (first 2000 chars only for performance)
            content_preview = file_ctx.raw_content[:2000].lower()
            for kw in keywords:
                if len(kw) > 2 and kw in content_preview:
                    score += 0.5

            if score > 0:
                scored_files.append((score, file_ctx))

        # Sort by score descending, take top N
        scored_files.sort(key=lambda x: x[0], reverse=True)
        return [f for _, f in scored_files[:max_files]]

    def _build_dependency_graph(
        self,
        context: ProjectContext,
    ) -> dict[str, list[str]]:
        """Build a simple dependency graph from file imports."""
        graph: dict[str, list[str]] = {}

        for file_ctx in context.files:
            file_key = str(file_ctx.path)
            graph[file_key] = []

            for imp in file_ctx.imports:
                # Check if import refers to another project file
                for other in context.files:
                    if other.path.stem == imp.split(".")[-1]:
                        graph[file_key].append(str(other.path))
                        break

        return graph

    def _format_git_info(self, git_info: dict[str, Any]) -> str:
        """Format git info for context package."""
        if not git_info.get("has_git"):
            return "No git repository detected."

        parts = [
            f"Branch: {git_info.get('branch', 'unknown')}",
        ]

        commits = git_info.get("recent_commits", [])
        if commits:
            parts.append("Recent commits:")
            parts.extend(f"  {c}" for c in commits[:5])

        return "\n".join(parts)
