"""Project structure extraction."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from terminal_ai_co_agent.logging.logger import get_logger

logger = get_logger(__name__)


class StructureExtractor:
    """Extract and analyze project directory structure."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def extract(self) -> dict[str, Any]:
        """Extract project structure overview."""
        structure = {
            "root": str(self.project_root),
            "type": self._detect_project_type(),
            "directories": self._list_directories(),
            "entry_points": self._find_entry_points(),
            "config_files": self._find_config_files(),
            "package_manager": self._detect_package_manager(),
            "build_system": self._detect_build_system(),
            "test_directory": self._find_test_directory(),
            "doc_directory": self._find_doc_directory(),
        }

        logger.debug("structure.extracted", type=structure["type"])
        return structure

    def get_tree(
        self,
        max_depth: int = 3,
        max_files_per_dir: int = 30,
    ) -> str:
        """Generate a tree-like representation of the project."""
        lines: list[str] = [f"{self.project_root.name}/"]

        def _walk(directory: Path, prefix: str, depth: int) -> None:
            if depth > max_depth:
                lines.append(f"{prefix}└── ...")
                return

            try:
                entries = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name))
            except PermissionError:
                return

            # Filter ignored
            entries = [e for e in entries if not self._should_ignore(e)]
            # Limit files shown
            dirs = [e for e in entries if e.is_dir()]
            files = [e for e in entries if not e.is_dir()]

            all_entries = dirs + files[:max_files_per_dir]
            if len(files) > max_files_per_dir:
                all_entries.append(None)  # Sentinel for "..."

            for i, entry in enumerate(all_entries):
                is_last = i == len(all_entries) - 1
                connector = "└── " if is_last else "├── "

                if entry is None:
                    lines.append(f"{prefix}{connector}... ({len(files) - max_files_per_dir} more files)")
                    continue

                if entry.is_dir():
                    lines.append(f"{prefix}{connector}{entry.name}/")
                    extension = "    " if is_last else "│   "
                    _walk(entry, prefix + extension, depth + 1)
                else:
                    lines.append(f"{prefix}{connector}{entry.name}")

        _walk(self.project_root, "", 0)
        return "\n".join(lines)

    # ── Detection Methods ───────────────────────────────────────

    def _detect_project_type(self) -> str:
        """Detect the type of project."""
        root = self.project_root

        if (root / "pyproject.toml").exists() or (root / "setup.py").exists():
            return "python"
        if (root / "package.json").exists():
            return "javascript/typescript"
        if (root / "go.mod").exists():
            return "go"
        if (root / "Cargo.toml").exists():
            return "rust"
        if (root / "pom.xml").exists() or (root / "build.gradle").exists():
            return "java"
        if (root / "Gemfile").exists():
            return "ruby"
        if (root / "composer.json").exists():
            return "php"
        if (root / "CMakeLists.txt").exists():
            return "c/c++"
        if (root / "Dockerfile").exists():
            return "docker"
        return "unknown"

    def _list_directories(self) -> list[str]:
        """List top-level directories."""
        dirs = []
        for entry in self.project_root.iterdir():
            if entry.is_dir() and not self._should_ignore(entry):
                dirs.append(entry.name)
        return sorted(dirs)

    def _find_entry_points(self) -> list[str]:
        """Find likely entry point files."""
        patterns = [
            "main.py", "app.py", "index.py", "run.py",
            "main.js", "index.js", "app.js", "server.js",
            "main.ts", "index.ts", "app.ts", "server.ts",
            "main.go", "main.rs", "Main.java",
        ]
        found = []
        for pattern in patterns:
            path = self.project_root / pattern
            if path.exists():
                found.append(str(path.relative_to(self.project_root)))
        return found

    def _find_config_files(self) -> list[str]:
        """Find configuration files."""
        config_patterns = [
            "*.toml", "*.yaml", "*.yml", "*.json", "*.ini",
            "*.cfg", "*.conf", ".env*", "Dockerfile*",
            "Makefile", "makefile", "*.mk",
        ]
        import fnmatch

        found = []
        for entry in self.project_root.iterdir():
            if entry.is_file():
                for pattern in config_patterns:
                    if fnmatch.fnmatch(entry.name, pattern):
                        found.append(entry.name)
                        break
        return sorted(found)

    def _detect_package_manager(self) -> str:
        """Detect package manager."""
        root = self.project_root
        checks = [
            ("uv", "uv.lock"),
            ("poetry", "poetry.lock"),
            ("pip", "requirements.txt"),
            ("pip", "Pipfile"),
            ("npm", "package-lock.json"),
            ("yarn", "yarn.lock"),
            ("pnpm", "pnpm-lock.yaml"),
            ("go mod", "go.sum"),
            ("cargo", "Cargo.lock"),
            ("bundler", "Gemfile.lock"),
            ("composer", "composer.lock"),
        ]
        for manager, file in checks:
            if (root / file).exists():
                return manager
        return "unknown"

    def _detect_build_system(self) -> str:
        """Detect build system."""
        root = self.project_root
        checks = [
            ("hatchling", "pyproject.toml"),
            ("setuptools", "setup.py"),
            ("webpack", "webpack.config.js"),
            ("vite", "vite.config.ts"),
            ("esbuild", "esbuild.config.js"),
            ("go build", "go.mod"),
            ("cargo", "Cargo.toml"),
            ("maven", "pom.xml"),
            ("gradle", "build.gradle"),
            ("cmake", "CMakeLists.txt"),
            ("make", "Makefile"),
        ]
        for system, file in checks:
            if (root / file).exists():
                return system
        return "unknown"

    def _find_test_directory(self) -> str | None:
        """Find test directory."""
        candidates = ["tests", "test", "spec", "__tests__", "test_suite"]
        for name in candidates:
            if (self.project_root / name).is_dir():
                return name
        return None

    def _find_doc_directory(self) -> str | None:
        """Find documentation directory."""
        candidates = ["docs", "doc", "documentation", ".github"]
        for name in candidates:
            if (self.project_root / name).is_dir():
                return name
        return None

    def _should_ignore(self, path: Path) -> bool:
        """Check if path should be ignored in structure view."""
        ignore_names = {
            ".git", "__pycache__", ".venv", "venv", "node_modules",
            ".mypy_cache", ".pytest_cache", ".ruff_cache", ".coagent",
            "dist", "build", ".egg-info", ".next", ".nuxt",
        }
        return path.name in ignore_names or path.name.startswith(".")
