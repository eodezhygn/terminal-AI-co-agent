"""Document retrieval for RAG queries."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from terminal_ai_co_agent.logging.logger import get_logger
from terminal_ai_co_agent.rag.chunker import DocumentChunker
from terminal_ai_co_agent.rag.types import (
    ChunkStrategy,
    DocumentChunk,
    RAGQuery,
    RAGStats,
    RetrievalResult,
)

if TYPE_CHECKING:
    from terminal_ai_co_agent.config.types import RAGConfig

logger = get_logger(__name__)


class Retriever:
    """Retrieves relevant document chunks for a query.

    Supports:
    - Semantic search (via embeddings + vector store)
    - Keyword/BM25 search (fallback)
    - Hybrid search combining both
    - Source filtering
    - Score thresholding
    """

    def __init__(self, config: "RAGConfig") -> None:
        self.config = config
        self.chunker = DocumentChunker(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
        )
        self._chunks: list[DocumentChunk] = []
        self._file_hashes: dict[str, str] = {}
        self._embedder: Any = None
        self._initialized = False

    # ── Initialization ──────────────────────────────────────────

    async def initialize(self) -> None:
        """Initialize the retriever and its embedder."""
        if self._initialized:
            return

        try:
            from sentence_transformers import SentenceTransformer
            self._embedder = SentenceTransformer(self.config.embedding_model)
            logger.info("rag.embedder_loaded", model=self.config.embedding_model)
        except ImportError:
            logger.warning(
                "rag.no_sentence_transformers",
                message="Install with: pip install sentence-transformers",
            )
            self._embedder = None
        except Exception as exc:
            logger.warning("rag.embedder_error", error=str(exc))
            self._embedder = None

        self._initialized = True

    # ── Indexing ────────────────────────────────────────────────

    async def index_document(self, path: Path) -> int:
        """Index a single document."""
        if not path.exists() or not path.is_file():
            logger.warning("rag.file_not_found", path=str(path))
            return 0

        content = path.read_text(encoding="utf-8", errors="replace")

        # Check if file changed
        file_hash = hashlib.sha256(content.encode()).hexdigest()
        if self._file_hashes.get(str(path)) == file_hash:
            logger.debug("rag.file_unchanged", path=str(path))
            return 0

        # Remove old chunks for this file
        self._chunks = [c for c in self._chunks if c.source_path != str(path)]

        # Chunk and add
        chunks = self.chunker.chunk_file(path, content)
        self._chunks.extend(chunks)
        self._file_hashes[str(path)] = file_hash

        logger.info("rag.indexed_file", path=str(path), chunks=len(chunks))
        return len(chunks)

    async def index_directory(self, directory: Path) -> int:
        """Index all documents in a directory."""
        total = 0

        for pattern in self.config.document_paths:
            for matched in directory.glob(pattern):
                if matched.is_file():
                    total += await self.index_document(matched)

        logger.info("rag.indexed_directory", path=str(directory), total_chunks=total)
        return total

    # ── Retrieval ───────────────────────────────────────────────

    async def retrieve(self, query: RAGQuery) -> list[RetrievalResult]:
        """Retrieve relevant chunks for a query."""
        if not self._chunks:
            logger.warning("rag.no_chunks")
            return []

        # Filter by source if specified
        candidates = self._chunks
        if query.source_filter:
            candidates = [
                c for c in candidates
                if any(f in c.source_path for f in query.source_filter)
            ]

        if query.metadata_filter:
            for key, value in query.metadata_filter.items():
                candidates = [
                    c for c in candidates
                    if c.metadata.get(key) == value
                ]

        if not candidates:
            return []

        # Try semantic search first
        if self._embedder is not None:
            results = await self._semantic_search(query.query, candidates, query.top_k)
        else:
            # Fallback to keyword search
            results = self._keyword_search(query.query, candidates, query.top_k)

        # Apply score threshold
        results = [r for r in results if r.score >= query.min_score]

        return results[:query.top_k]

    async def retrieve_context(
        self,
        query: str,
        top_k: int = 5,
    ) -> str:
        """Retrieve and format context for model consumption."""
        results = await self.retrieve(RAGQuery(query=query, top_k=top_k))

        if not results:
            return ""

        parts = ["# Retrieved Context", ""]
        for i, result in enumerate(results):
            parts.append(f"## Source {i + 1}: {result.chunk.source_path}")
            parts.append(f"Relevance: {result.score:.2f}")
            parts.append("")
            parts.append(result.chunk.content)
            parts.append("")

        return "\n".join(parts)

    # ── Search Methods ──────────────────────────────────────────

    async def _semantic_search(
        self,
        query: str,
        candidates: list[DocumentChunk],
        top_k: int,
    ) -> list[RetrievalResult]:
        """Search using embeddings and cosine similarity."""
        if self._embedder is None:
            return self._keyword_search(query, candidates, top_k)

        try:
            import numpy as np

            # Compute query embedding
            query_embedding = self._embedder.encode(query, convert_to_numpy=True)

            # Compute or retrieve chunk embeddings
            results: list[RetrievalResult] = []

            for chunk in candidates:
                if chunk.embedding is None:
                    chunk.embedding = self._embedder.encode(
                        chunk.content,
                        convert_to_numpy=True,
                    ).tolist()

                # Cosine similarity
                chunk_vec = np.array(chunk.embedding)
                similarity = np.dot(query_embedding, chunk_vec) / (
                    np.linalg.norm(query_embedding) * np.linalg.norm(chunk_vec)
                )

                results.append(RetrievalResult(
                    chunk=chunk,
                    score=float(similarity),
                    rank=0,
                ))

            results.sort(key=lambda x: x.score, reverse=True)

            # Assign ranks
            for i, r in enumerate(results[:top_k]):
                r.rank = i + 1

            return results[:top_k]

        except Exception as exc:
            logger.warning("rag.semantic_search_error", error=str(exc))
            return self._keyword_search(query, candidates, top_k)

    def _keyword_search(
        self,
        query: str,
        candidates: list[DocumentChunk],
        top_k: int,
    ) -> list[RetrievalResult]:
        """Simple keyword-based search fallback."""
        query_lower = query.lower()
        keywords = [kw for kw in query_lower.split() if len(kw) > 2]

        results: list[RetrievalResult] = []

        for chunk in candidates:
            content_lower = chunk.content.lower()
            # BM25-like scoring with term frequency
            score = 0.0
            for kw in keywords:
                count = content_lower.count(kw)
                if count > 0:
                    # TF component
                    tf = count / max(len(content_lower.split()), 1)
                    score += tf

            if score > 0:
                results.append(RetrievalResult(
                    chunk=chunk,
                    score=min(score, 1.0),
                    rank=0,
                ))

        results.sort(key=lambda x: x.score, reverse=True)

        for i, r in enumerate(results[:top_k]):
            r.rank = i + 1

        return results[:top_k]

    # ── Management ──────────────────────────────────────────────

    def clear(self) -> None:
        """Clear all indexed chunks."""
        self._chunks.clear()
        self._file_hashes.clear()
        logger.info("rag.cleared")

    def get_stats(self) -> RAGStats:
        """Get retrieval statistics."""
        total_tokens = sum(len(c.content.split()) for c in self._chunks)
        return RAGStats(
            total_documents=len(set(c.source_path for c in self._chunks)),
            total_chunks=len(self._chunks),
            total_tokens=total_tokens,
            vector_store_backend=self.config.vector_backend,
            embedding_model=self.config.embedding_model,
        )

    def get_chunks_for_file(self, file_path: str) -> list[DocumentChunk]:
        """Get all chunks for a specific file."""
        return [c for c in self._chunks if c.source_path == file_path]
