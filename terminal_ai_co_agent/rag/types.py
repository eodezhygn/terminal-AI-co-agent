"""Type definitions for the RAG subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ChunkStrategy(str, Enum):
    """Strategies for chunking documents."""

    FIXED_SIZE = "fixed_size"
    SENTENCE = "sentence"
    PARAGRAPH = "paragraph"
    SEMANTIC = "semantic"
    CODE_BLOCK = "code_block"


@dataclass
class DocumentChunk:
    """A chunk of a document with metadata."""

    id: str
    content: str
    source_path: str
    chunk_index: int
    total_chunks: int
    embedding: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    start_line: int = 0
    end_line: int = 0


@dataclass
class RetrievalResult:
    """A single retrieval result."""

    chunk: DocumentChunk
    score: float
    rank: int


@dataclass
class RAGQuery:
    """A query against the RAG system."""

    query: str
    top_k: int = 5
    min_score: float = 0.0
    source_filter: list[str] | None = None  # Filter by source file
    metadata_filter: dict[str, Any] | None = None


@dataclass
class RAGStats:
    """Statistics about the RAG system."""

    total_documents: int
    total_chunks: int
    total_tokens: int
    vector_store_backend: str
    embedding_model: str
    last_indexed: str = ""
