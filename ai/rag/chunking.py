"""
chunking.py
-----------
Splits raw documents (policies, FAQs, complaint history, etc.) into
overlapping text chunks that are small enough to embed accurately
but large enough to retain context.

Used by: ai/rag/chunking.py in the Resolvix-AI project structure.
"""

from dataclasses import dataclass, field
from typing import List, Optional
import re
import uuid


@dataclass
class Chunk:
    id: str
    text: str
    source: str
    chunk_index: int
    metadata: dict = field(default_factory=dict)


class TextChunker:
    """
    Recursive character-based chunker with overlap.
    Tries to split on paragraph/sentence boundaries first so chunks
    don't get cut mid-sentence -- this materially improves retrieval
    quality and is worth calling out in a demo/judge Q&A.
    """

    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 120,
        separators: Optional[List[str]] = None,
    ):
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or ["\n\n", "\n", ". ", " "]

    def _split_on_separator(self, text: str, separators: List[str]) -> List[str]:
        if not separators:
            return [text]
        sep, rest = separators[0], separators[1:]
        if sep not in text:
            return self._split_on_separator(text, rest)
        parts = [p for p in text.split(sep) if p.strip()]
        return parts

    def _merge_parts(self, parts: List[str]) -> List[str]:
        """Greedily merge small parts into chunk_size-sized windows with overlap."""
        chunks, current = [], ""
        for part in parts:
            candidate = (current + " " + part).strip() if current else part
            if len(candidate) <= self.chunk_size:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                # start new chunk, carrying overlap from the tail of the previous one
                overlap_text = current[-self.chunk_overlap:] if current else ""
                current = (overlap_text + " " + part).strip()
                # if a single part is bigger than chunk_size, hard-split it
                while len(current) > self.chunk_size:
                    chunks.append(current[: self.chunk_size])
                    current = current[self.chunk_size - self.chunk_overlap :]
        if current:
            chunks.append(current)
        return chunks

    def chunk_text(self, text: str, source: str = "unknown", metadata: Optional[dict] = None) -> List[Chunk]:
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return []
        parts = self._split_on_separator(text, self.separators)
        merged = self._merge_parts(parts)
        return [
            Chunk(
                id=str(uuid.uuid4()),
                text=chunk_text,
                source=source,
                chunk_index=i,
                metadata=metadata or {},
            )
            for i, chunk_text in enumerate(merged)
        ]

    def chunk_documents(self, documents: List[dict]) -> List[Chunk]:
        """
        documents: [{"text": str, "source": str, "metadata": dict}, ...]
        e.g. loaded from data/policies/*.pdf after text extraction.
        """
        all_chunks: List[Chunk] = []
        for doc in documents:
            all_chunks.extend(
                self.chunk_text(
                    doc["text"],
                    source=doc.get("source", "unknown"),
                    metadata=doc.get("metadata", {}),
                )
            )
        return all_chunks


if __name__ == "__main__":
    sample = """
    Refund Policy: Customers are eligible for a full refund within 30 days
    of purchase provided the item is unused and in original packaging.

    Warranty Policy: All electronics carry a 1-year manufacturer warranty
    covering defects but not accidental damage.
    """
    chunker = TextChunker(chunk_size=120, chunk_overlap=20)
    for c in chunker.chunk_text(sample, source="policy_docs.pdf"):
        print(f"[{c.chunk_index}] ({len(c.text)} chars) {c.text[:80]}...")
