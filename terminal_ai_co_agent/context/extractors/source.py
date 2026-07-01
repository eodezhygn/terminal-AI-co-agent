"""Source code context extraction using tree-sitter."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from terminal_ai_co_agent.context.types import (
    ContextSource,
    FileContext,
    SymbolInfo,
)
from terminal_ai_co_agent.logging.logger import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

# Language mapping: file extension → tree-sitter language
EXTENSION_LANGUAGE_MAP: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".sql": "sql",
    ".sh": "bash",
    ".bash": "bash",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".md": "markdown",
    ".html": "html",
    ".css": "css",
}

# Files to always ignore
IGNORE_PATTERNS: list[str] = [
    "node_modules",
    "__pycache__",
    ".git",
    ".venv",
    "venv",
    ".env",
    "dist",
    "build",
    ".coagent",
    "*.pyc",
    "*.pyo",
    "*.egg-info",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
]


class SourceExtractor:
    """Extract structured context from source code files.

    Uses tree-sitter for AST-level understanding when available,
    falls back to regex-based extraction for unsupported languages.
    """

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root or Path.cwd()
        self._parsers: dict[str, Any] = {}
        self._init_parsers()

    def _init_parsers(self) -> None:
        """Initialize available tree-sitter parsers."""
        try:
            import tree_sitter_python
            import tree_sitter_javascript
            import tree_sitter_typescript

            self._parsers["python"] = tree_sitter_python
            self._parsers["javascript"] = tree_sitter_javascript
            self._parsers["typescript"] = tree_sitter_typescript
            logger.debug("tree_sitter.initialized", languages=list(self._parsers.keys()))
        except ImportError:
            logger.warning("tree_sitter.not_available", message="Falling back to regex extraction")

    def extract_file(self, path: Path) -> FileContext | None:
        """Extract context from a single source file."""
        if not path.exists() or not path.is_file():
            return None

        if self._should_ignore(path):
            return None

        language = self._detect_language(path)
        if not language:
            return None

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            logger.warning("source.read_error", path=str(path), error=str(exc))
            return None

        return FileContext(
            path=path.relative_to(self.project_root),
            source=ContextSource.SOURCE_CODE,
            language=language,
            summary=self._generate_summary(path, content, language),
            symbols=self._extract_symbols(content, language),
            imports=self._extract_imports(content, language),
            raw_content=content,
            metadata={
                "lines": len(content.splitlines()),
                "size": len(content),
                "extension": path.suffix,
            },
        )

    def extract_directory(
        self,
        directory: Path | None = None,
        *,
        max_files: int = 500,
    ) -> list[FileContext]:
        """Extract context from all source files in a directory."""
        target = directory or self.project_root
        contexts: list[FileContext] = []

        for path in target.rglob("*"):
            if len(contexts) >= max_files:
                logger.warning("source.max_files_reached", max_files=max_files)
                break

            if self._should_ignore(path):
                continue

            ctx = self.extract_file(path)
            if ctx:
                contexts.append(ctx)

        logger.info("source.directory_extracted", path=str(target), files=len(contexts))
        return contexts

    # ── Symbol Extraction ───────────────────────────────────────

    def _extract_symbols(self, content: str, language: str) -> list[SymbolInfo]:
        """Extract symbols (functions, classes, etc.) from source code."""
        parser = self._parsers.get(language)

        if parser and language == "python":
            return self._extract_python_symbols(content, parser)
        elif parser and language in ("javascript", "typescript"):
            return self._extract_js_symbols(content, parser, language)
        else:
            return self._extract_symbols_regex(content, language)

    def _extract_python_symbols(self, content: str, parser: Any) -> list[SymbolInfo]:
        """Extract Python symbols using tree-sitter."""
        import tree_sitter

        try:
            language = parser.language()
            tree_parser = tree_sitter.Parser()
            tree_parser.set_language(language)
            tree = tree_parser.parse(content.encode("utf-8"))
        except Exception as exc:
            logger.debug("source.tree_sitter_parse_error", error=str(exc))
            return self._extract_symbols_regex(content, "python")

        symbols: list[SymbolInfo] = []
        self._walk_python_tree(tree.root_node, content, symbols)
        return symbols

    def _walk_python_tree(
        self,
        node: Any,
        content: str,
        symbols: list[SymbolInfo],
        parent: SymbolInfo | None = None,
    ) -> None:
        """Walk a Python tree-sitter AST to find symbols."""
        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = content[name_node.start_byte:name_node.end_byte]
                params = self._extract_params(node, content)
                symbol = SymbolInfo(
                    name=name,
                    kind="method" if parent and parent.kind == "class" else "function",
                    line=node.start_point[0] + 1,
                    signature=f"{name}({params})",
                    docstring=self._extract_docstring(node, content),
                )
                if parent:
                    parent.children.append(symbol)
                else:
                    symbols.append(symbol)

        elif node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = content[name_node.start_byte:name_node.end_byte]
                symbol = SymbolInfo(
                    name=name,
                    kind="class",
                    line=node.start_point[0] + 1,
                    signature=f"class {name}",
                    docstring=self._extract_docstring(node, content),
                )
                symbols.append(symbol)
                # Walk children with this class as parent
                for child in node.children:
                    self._walk_python_tree(child, content, symbols, symbol)

        else:
            for child in node.children:
                self._walk_python_tree(child, content, symbols, parent)

    def _extract_js_symbols(
        self,
        content: str,
        parser: Any,
        language: str,
    ) -> list[SymbolInfo]:
        """Extract JavaScript/TypeScript symbols using tree-sitter."""
        import tree_sitter

        try:
            tree_lang = parser.language()
            tree_parser = tree_sitter.Parser()
            tree_parser.set_language(tree_lang)
            tree = tree_parser.parse(content.encode("utf-8"))
        except Exception:
            return self._extract_symbols_regex(content, language)

        symbols: list[SymbolInfo] = []
        self._walk_js_tree(tree.root_node, content, symbols)
        return symbols

    def _walk_js_tree(
        self,
        node: Any,
        content: str,
        symbols: list[SymbolInfo],
    ) -> None:
        """Walk a JS/TS tree-sitter AST to find symbols."""
        if node.type in ("function_declaration", "method_definition"):
            name_node = node.child_by_field_name("name")
            if name_node:
                name = content[name_node.start_byte:name_node.end_byte]
                params = self._extract_params(node, content)
                symbols.append(
                    SymbolInfo(
                        name=name,
                        kind="function",
                        line=node.start_point[0] + 1,
                        signature=f"{name}({params})",
                    )
                )
        elif node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = content[name_node.start_byte:name_node.end_byte]
                symbols.append(
                    SymbolInfo(
                        name=name,
                        kind="class",
                        line=node.start_point[0] + 1,
                        signature=f"class {name}",
                    )
                )

        for child in node.children:
            self._walk_js_tree(child, content, symbols)

    def _extract_symbols_regex(
        self,
        content: str,
        language: str,
    ) -> list[SymbolInfo]:
        """Fallback regex-based symbol extraction."""
        import re

        symbols: list[SymbolInfo] = []

        if language == "python":
            # Match function definitions
            for match in re.finditer(
                r"^\s*def\s+(\w+)\s*\(([^)]*)\)\s*(?:->[^:]*)?:",
                content,
                re.MULTILINE,
            ):
                symbols.append(
                    SymbolInfo(
                        name=match.group(1),
                        kind="function",
                        line=content[:match.start()].count("\n") + 1,
                        signature=f"{match.group(1)}({match.group(2)})",
                    )
                )
            # Match class definitions
            for match in re.finditer(
                r"^\s*class\s+(\w+)\s*(?:\(([^)]*)\))?\s*:",
                content,
                re.MULTILINE,
            ):
                symbols.append(
                    SymbolInfo(
                        name=match.group(1),
                        kind="class",
                        line=content[:match.start()].count("\n") + 1,
                        signature=f"class {match.group(1)}",
                    )
                )

        elif language in ("javascript", "typescript"):
            for match in re.finditer(
                r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)",
                content,
                re.MULTILINE,
            ):
                symbols.append(
                    SymbolInfo(
                        name=match.group(1),
                        kind="function",
                        line=content[:match.start()].count("\n") + 1,
                        signature=f"{match.group(1)}({match.group(2)})",
                    )
                )
            for match in re.finditer(
                r"(?:export\s+)?class\s+(\w+)",
                content,
                re.MULTILINE,
            ):
                symbols.append(
                    SymbolInfo(
                        name=match.group(1),
                        kind="class",
                        line=content[:match.start()].count("\n") + 1,
                    )
                )

        return symbols

    # ── Import Extraction ───────────────────────────────────────

    def _extract_imports(self, content: str, language: str) -> list[str]:
        """Extract import/dependency statements."""
        import re

        imports: list[str] = []

        if language == "python":
            patterns = [
                r"^import\s+(\S+)",
                r"^from\s+(\S+)\s+import",
            ]
        elif language in ("javascript", "typescript"):
            patterns = [
                r"(?:import\s+.*?\s+from\s+['\"])([^'\"]+)",
                r"require\s*\(\s*['\"]([^'\"]+)",
            ]
        else:
            return imports

        for pattern in patterns:
            for match in re.finditer(pattern, content, re.MULTILINE):
                imp = match.group(1)
                if imp not in imports:
                    imports.append(imp)

        return imports

    # ── Helpers ─────────────────────────────────────────────────

    def _generate_summary(self, path: Path, content: str, language: str) -> str:
        """Generate a brief summary of a source file."""
        lines = content.splitlines()
        symbols = self._extract_symbols(content, language)

        summary_parts = [
            f"File: {path.name}",
            f"Language: {language}",
            f"Lines: {len(lines)}",
        ]

        if symbols:
            funcs = [s for s in symbols if s.kind == "function"]
            classes = [s for s in symbols if s.kind == "class"]
            if classes:
                summary_parts.append(f"Classes: {len(classes)} ({', '.join(c.name for c in classes[:5])})")
            if funcs:
                summary_parts.append(f"Functions: {len(funcs)} ({', '.join(f.name for f in funcs[:5])})")

        return " | ".join(summary_parts)

    def _extract_params(self, node: Any, content: str) -> str:
        """Extract parameter list from a function node."""
        params_node = node.child_by_field_name("parameters")
        if params_node:
            return content[params_node.start_byte:params_node.end_byte].strip("()")
        return ""

    def _extract_docstring(self, node: Any, content: str) -> str:
        """Extract docstring from a function/class node."""
        body = node.child_by_field_name("body")
        if body and body.children:
            first = body.children[0]
            if first.type == "expression_statement":
                expr = first.children[0] if first.children else None
                if expr and expr.type == "string":
                    return content[expr.start_byte:expr.end_byte].strip('"""\'')
        return ""

    def _detect_language(self, path: Path) -> str | None:
        """Detect programming language from file extension."""
        ext = path.suffix.lower()
        # Handle compound extensions like .test.ts → .ts
        while ext:
            if ext in EXTENSION_LANGUAGE_MAP:
                return EXTENSION_LANGUAGE_MAP[ext]
            # Strip the first part of compound extension
            stem = path.stem
            if "." in stem:
                ext = "." + stem.split(".")[-1] + ext
            else:
                break
        return EXTENSION_LANGUAGE_MAP.get(ext)

    def _should_ignore(self, path: Path) -> bool:
        """Check if path should be ignored."""
        import fnmatch

        path_str = str(path)
        for pattern in IGNORE_PATTERNS:
            if fnmatch.fnmatch(path.name, pattern) or pattern in path_str.split(str(Path("/"))):
                return True

        # Skip binary and very large files
        if path.suffix in (".pyc", ".pyo", ".so", ".dll", ".exe", ".bin", ".dat"):
            return True

        try:
            if path.stat().st_size > 1_000_000:  # 1 MB
                return True
        except Exception:
            return True

        return False
