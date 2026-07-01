"""RAG subsystem — retrieval-augmented generation for context enrichment."""

from terminal_ai_co_agent.rag.engine import RAGEngine
from terminal_ai_co_agent.rag.retriever import Retriever
from terminal_ai_co_agent.rag.types import (
    ChunkStrategy,
    DocumentChunk,
    RAGQuery,
    RAGStats,
    RetrievalResult,
)

__all__ = [
    "RAGEngine",
    "Retriever",
    "DocumentChunk",
    "RAGQuery",
    "RAGStats",
    "RetrievalResult",
    "ChunkStrategy",
]

