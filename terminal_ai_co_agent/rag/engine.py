"""RAG engine — coordinates indexing, retrieval, and context injection."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from terminal_ai_co_agent.logging.audit import audit_event
from terminal_ai_co_agent.logging.logger import get_logger
from terminal_ai_co_agent.rag.retriever import Retriever
from terminal_ai_co_agent.rag.types import RAGQuery, RetrievalResult

if TYPE_CHECKING:
    from terminal_ai_co_agent.config.types import CoAgentConfig

logger = get_logger(__name__)


class RAGEngine:
    """RAG (Retrieval-Augmented Generation) engine.

    Provides context-enriched prompts by retrieving relevant
    project documentation, code, and knowledge base entries.

    Usage:
        engine = RAGEngine(config)
        await engine.initialize()
        await engine.index_project()
        context = await engine.augment_query("How does auth work?")
    """

    def __init__(self, config: "CoAgentConfig") -> None:
        self.config = config
        self.rag_config = config.rag
        self.retriever = Retriever(self.rag_config)
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the RAG engine."""
        if not self.rag_config.enabled:
            logger.info("rag.disabled")
            return

        await self.retriever.initialize()
        self._initialized = True
        logger.info("rag.initialized")

    # ── Indexing ────────────────────────────────────────────────

    async def index_project(self, project_root: Path | None = None) -> int:
        """Index all configured document paths in the project."""
        if not self.rag_config.enabled:
            return 0

        root = project_root or self.config.general.project_root
        total = 0

        for doc_path in self.rag_config.document_paths:
            full_path = root / doc_path if not Path(doc_path).is_absolute() else Path(doc_path)

            if full_path.is_file():
                total += await self.retriever.index_document(full_path)
            elif full_path.is_dir():
                total += await self.retriever.index_directory(full_path)
            elif "*" in str(doc_path) or "?" in str(doc_path):
                # Glob pattern
                total += await self.retriever.index_directory(root)

        audit_event("rag_indexed", total_chunks=total, project_root=str(root))
        logger.info("rag.project_indexed", total_chunks=total)

        return total

    async def index_file(self, path: Path) -> int:
        """Index a single file."""
        if not self.rag_config.enabled:
            return 0

        return await self.retriever.index_document(path)

    # ── Retrieval ───────────────────────────────────────────────

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        source_filter: list[str] | None = None,
    ) -> list[RetrievalResult]:
        """Retrieve relevant chunks."""
        if not self._initialized:
            return []

        return await self.retriever.retrieve(
            RAGQuery(
                query=query,
                top_k=top_k,
                source_filter=source_filter,
            )
        )

    async def augment_query(
        self,
        query: str,
        top_k: int = 5,
    ) -> str:
        """Augment a query with retrieved context.

        Returns formatted context string that can be prepended
        to a prompt for the reasoning model.
        """
        if not self._initialized or not self.rag_config.enabled:
            return query

        context = await self.retriever.retrieve_context(query, top_k)
        if not context:
            return query

        logger.debug("rag.query_augmented", query=query[:100], chunks=top_k)
        return context

    async def augment_prompt(
        self,
        prompt: str,
        top_k: int = 5,
    ) -> str:
        """Augment a full prompt with retrieved context.

        Returns the prompt with relevant context inserted.
        """
        context = await self.augment_query(prompt, top_k)
        if context == prompt:
            return prompt

        return f"{context}\n\n---\n\n# User Query\n{prompt}"

    # ── Management ──────────────────────────────────────────────

    def clear_index(self) -> None:
        """Clear the entire index."""
        self.retriever.clear()
        logger.info("rag.index_cleared")

    async def reindex(self, project_root: Path | None = None) -> int:
        """Clear and rebuild the entire index."""
        self.clear_index()
        return await self.index_project(project_root)

    def get_stats(self) -> dict[str, Any]:
        """Get RAG statistics."""
        if not self._initialized:
            return {"enabled": False, "initialized": False}

        stats = self.retriever.get_stats()
        return {
            "enabled": self.rag_config.enabled,
            "initialized": self._initialized,
            "total_documents": stats.total_documents,
            "total_chunks": stats.total_chunks,
            "total_tokens": stats.total_tokens,
            "embedding_model": stats.embedding_model,
            "vector_backend": stats.vector_store_backend,
        }

    @property
    def is_ready(self) -> bool:
        """Check if RAG is initialized and has indexed content."""
        if not self._initialized:
            return False
        stats = self.retriever.get_stats()
        return stats.total_chunks > 0
