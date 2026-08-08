"""
pipeline.py
-----------
End-to-end RAG pipeline: Chunking -> Embedding -> Vector DB -> Retriever -> Generator.
This is the module your Policy Agent / other agents call into.

Usage:
    pipeline = RAGPipeline()
    pipeline.ingest_documents([{"text": "...", "source": "Refund Policy.pdf"}])
    result = pipeline.query("Can I get a refund after 20 days?")
    print(result.answer, result.confidence)
"""

from typing import List

from .chunking import TextChunker
from .embedding import EmbeddingModel
from .vectordb import VectorDB
from .retriever import Retriever
from .generator import Generator, GeneratedResponse


class RAGPipeline:
    def __init__(
        self,
        persist_path: str = "data/vector_store",
        embedding_provider: str = "local",
        generation_provider: str = "anthropic",
        chunk_size: int = 800,
        chunk_overlap: int = 120,
        top_k: int = 5,
        min_score: float = 0.3,
        use_reranker: bool = False,
    ):
        self.chunker = TextChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        self.embedder = EmbeddingModel(provider=embedding_provider)
        self.vectordb = VectorDB(persist_path=persist_path)
        self.retriever = Retriever(
            self.embedder, self.vectordb, top_k=top_k, min_score=min_score, use_reranker=use_reranker
        )
        self.generator = Generator(provider=generation_provider)

    def ingest_documents(self, documents: List[dict]):
        """documents: [{"text": str, "source": str, "metadata": dict?}, ...]"""
        chunks = self.chunker.chunk_documents(documents)
        embeddings = self.embedder.embed_texts([c.text for c in chunks])
        self.vectordb.add_chunks(chunks, embeddings)
        return len(chunks)

    def query(self, question: str) -> GeneratedResponse:
        retrieved = self.retriever.retrieve(question)
        return self.generator.generate(question, retrieved)


if __name__ == "__main__":
    pipeline = RAGPipeline(persist_path="./data/vector_store")

    docs = [
        {"text": "Customers are eligible for a full refund within 30 days of purchase provided the item is unused.", "source": "Refund Policy.pdf"},
        {"text": "All electronics carry a 1-year manufacturer warranty covering defects but not accidental damage.", "source": "Warranty Policy.pdf"},
    ]
    n = pipeline.ingest_documents(docs)
    print(f"Ingested {n} chunks")

    result = pipeline.query("Can I return a laptop I bought 20 days ago?")
    print("Answer:", result.answer)
    print("Confidence:", result.confidence)
    print("Sources:", result.cited_sources)
