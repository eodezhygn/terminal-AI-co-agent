"""Document chunking strategies for RAG ingestion."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from terminal_ai_co_agent.logging.logger import get_logger
from terminal_ai_co_agent.rag.types import ChunkStrategy, DocumentChunk

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class DocumentChunker:
    """Chunks documents into manageable pieces for embedding and retrieval.

    Supports multiple chunking strategies optimized for different content types.
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        strategy: ChunkStrategy = ChunkStrategy.FIXED_SIZE,
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = min(chunk_overlap, chunk_size // 2)
        self.strategy = strategy

    def chunk_file(self, path: Path, content: str) -> list[DocumentChunk]:
        """Chunk a single file's content."""
        # Detect content type and choose strategy
        strategy = self._detect_strategy(path, content)

        if strategy == ChunkStrategy.CODE_BLOCK:
            chunks = self._chunk_code(content)
        elif strategy == ChunkStrategy.PARAGRAPH:
            chunks = self._chunk_paragraphs(content)
        elif strategy == ChunkStrategy.SENTENCE:
            chunks = self._chunk_sentences(content)
        else:
            chunks = self._chunk_fixed_size(content)

        # Add metadata
        source = str(path)
        total = len(chunks)
        result: list[DocumentChunk] = []

        for i, chunk_content in enumerate(chunks):
            result.append(DocumentChunk(
                id=str(uuid.uuid4())[:12],
                content=chunk_content,
                source_path=source,
                chunk_index=i,
                total_chunks=total,
                metadata={
                    "file_name": path.name,
                    "file_extension": path.suffix,
                    "strategy": strategy.value,
                },
            ))

        logger.debug(
            "rag.chunked",
            file=path.name,
            chunks=total,
            strategy=strategy.value,
        )

        return result

    def chunk_text(self, text: str, source: str = "inline") -> list[DocumentChunk]:
        """Chunk arbitrary text (not from a file)."""
        chunks = self._chunk_fixed_size(text)
        total = len(chunks)

        return [
            DocumentChunk(
                id=str(uuid.uuid4())[:12],
                content=chunk,
                source_path=source,
                chunk_index=i,
                total_chunks=total,
            )
            for i, chunk in enumerate(chunks)
        ]

    # ── Chunking Strategies ─────────────────────────────────────

    def _chunk_fixed_size(self, text: str) -> list[str]:
        """Chunk text into fixed-size overlapping windows."""
        if len(text) <= self.chunk_size:
            return [text] if text.strip() else []

        chunks: list[str] = []
        start = 0

        while start < len(text):
            end = start + self.chunk_size
            chunk = text[start:end]

            # Try to break at a natural boundary
            if end < len(text):
                # Look for a good break point near the end
                break_candidates = ["\n\n", "\n", ". ", " ", ""]
                for candidate in break_candidates:
                    last_break = chunk.rfind(candidate, self.chunk_size - self.chunk_overlap)
                    if last_break > 0:
                        chunk = chunk[:last_break]
                        start = start + last_break + 1
                        break
                else:
                    start = end - self.chunk_overlap
            else:
                start = end

            if chunk.strip():
                chunks.append(chunk.strip())

        return chunks

    def _chunk_paragraphs(self, text: str) -> list[str]:
        """Chunk by paragraphs, merging small ones."""
        paragraphs = re.split(r"\n\s*\n", text)
        chunks: list[str] = []
        current = ""

        for para in paragraphs:
            if len(current) + len(para) <= self.chunk_size:
                current += ("\n\n" if current else "") + para
            else:
                if current.strip():
                    chunks.append(current.strip())
                current = para

        if current.strip():
            chunks.append(current.strip())

        return chunks

    def _chunk_sentences(self, text: str) -> list[str]:
        """Chunk by sentences, grouping up to chunk_size."""
        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks: list[str] = []
        current = ""

        for sentence in sentences:
            if len(current) + len(sentence) <= self.chunk_size:
                current += (" " if current else "") + sentence
            else:
                if current.strip():
                    chunks.append(current.strip())
                current = sentence

        if current.strip():
            chunks.append(current.strip())

        return chunks

    def _chunk_code(self, text: str) -> list[str]:
        """Chunk code by logical blocks (functions, classes, etc.)."""
        lines = text.splitlines()
        chunks: list[str] = []
        current_lines: list[str] = []
        current_length = 0
        in_block = False

        for line in lines:
            # Detect block starts
            stripped = line.strip()
            is_block_start = (
                stripped.startswith("def ")
                or stripped.startswith("class ")
                or stripped.startswith("export ")
                or stripped.startswith("function ")
                or stripped.startswith("## ")
                or stripped.startswith("# ")
                or stripped.startswith("// ")
                or stripped == "---"  # YAML separator
            )

            if is_block_start and current_length > self.chunk_size * 0.5:
                # Start new chunk
                if current_lines:
                    chunks.append("\n".join(current_lines))
                current_lines = [line]
                current_length = len(line)
                in_block = True
            else:
                current_lines.append(line)
                current_length += len(line)
                in_block = bool(stripped) and not is_block_start

                # Break if chunk gets too large
                if current_length >= self.chunk_size:
                    chunks.append("\n".join(current_lines))
                    current_lines = []
                    current_length = 0

        if current_lines:
            chunks.append("\n".join(current_lines))

        # Merge small chunks
        merged: list[str] = []
        buffer = ""
        for chunk in chunks:
            if len(buffer) + len(chunk) <= self.chunk_size:
                buffer += ("\n" if buffer else "") + chunk
            else:
                if buffer.strip():
                    merged.append(buffer.strip())
                buffer = chunk
        if buffer.strip():
            merged.append(buffer.strip())

        return merged or [text]

    def _detect_strategy(self, path: Path, content: str) -> ChunkStrategy:
        """Detect the best chunking strategy for a file."""
        ext = path.suffix.lower()

        # Code files → code block chunking
        code_extensions = {
            ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs",
            ".java", ".cpp", ".c", ".h", ".rb", ".php", ".swift",
            ".kt", ".scala", ".sql", ".sh", ".bash",
        }
        if ext in code_extensions:
            return ChunkStrategy.CODE_BLOCK

        # Config files → paragraph (they're usually short)
        config_extensions = {".yaml", ".yml", ".toml", ".json", ".ini", ".cfg"}
        if ext in config_extensions:
            return ChunkStrategy.PARAGRAPH if len(content) > 2000 else ChunkStrategy.FIXED_SIZE

        # Documentation → paragraph
        doc_extensions = {".md", ".rst", ".txt", ".adoc", ".org"}
        if ext in doc_extensions:
            return ChunkStrategy.PARAGRAPH

        return self.strategy
