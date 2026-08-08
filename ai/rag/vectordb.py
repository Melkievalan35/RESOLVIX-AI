"""
vectordb.py
-----------
Persistent vector store wrapper built on ChromaDB (embedded, file-based,
zero external infra -- perfect for a 24hr hackathon; swap for
Pinecone/Weaviate/Qdrant later without touching the rest of the pipeline).

Used by: ai/rag/vectordb.py
Storage path matches project structure: data/vector_store/
"""

from typing import List, Optional
import chromadb
from chromadb.config import Settings

from .chunking import Chunk


class VectorDB:
    def __init__(self, persist_path: str = "data/vector_store", collection_name: str = "resolvix_kb"):
        self.client = chromadb.PersistentClient(path=persist_path, settings=Settings(anonymized_telemetry=False))
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},  # cosine similarity for normalized embeddings
        )

    def add_chunks(self, chunks: List[Chunk], embeddings: List[List[float]]):
        if not chunks:
            return
        self.collection.add(
            ids=[c.id for c in chunks],
            embeddings=embeddings,
            documents=[c.text for c in chunks],
            metadatas=[{"source": c.source, "chunk_index": c.chunk_index, **c.metadata} for c in chunks],
        )

    def similarity_search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        filter_metadata: Optional[dict] = None,
    ) -> List[dict]:
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=filter_metadata or None,
        )
        hits = []
        for i in range(len(results["ids"][0])):
            hits.append(
                {
                    "id": results["ids"][0][i],
                    "text": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    # Chroma returns cosine distance; convert to a 0-1 similarity score
                    "score": 1 - results["distances"][0][i],
                }
            )
        return hits

    def count(self) -> int:
        return self.collection.count()

    def delete_by_source(self, source: str):
        self.collection.delete(where={"source": source})


if __name__ == "__main__":
    from embedding import EmbeddingModel
    from chunking import TextChunker

    chunker = TextChunker(chunk_size=200, chunk_overlap=30)
    chunks = chunker.chunk_text(
        "Refund policy allows returns within 30 days of purchase for unused items.",
        source="refund_policy.pdf",
    )
    embedder = EmbeddingModel(provider="local")
    vecs = embedder.embed_texts([c.text for c in chunks])

    db = VectorDB(persist_path="./data/vector_store")
    db.add_chunks(chunks, vecs)
    print(f"Indexed {db.count()} chunks")

    query_vec = embedder.embed_query("What is the refund window?")
    for hit in db.similarity_search(query_vec, top_k=2):
        print(f"score={hit['score']:.3f} | {hit['text'][:80]}")
