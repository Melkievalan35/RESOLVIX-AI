"""
retriever.py

Semantic retrieval over the Resolvix knowledge base.
"""

from dataclasses import dataclass
from typing import List, Optional

from .embedding import EmbeddingModel
from .vectordb import VectorDB


@dataclass
class RetrievedChunk:
    text: str
    source: str
    score: float
    metadata: dict


class Retriever:

    def __init__(
        self,
        embedder: EmbeddingModel,
        vectordb: VectorDB,
        top_k: int = 5,
        min_score: float = 0.30,
        use_reranker: bool = False,
    ):

        self.embedder = embedder
        self.vectordb = vectordb
        self.top_k = top_k
        self.min_score = min_score
        self.use_reranker = use_reranker
        self._reranker = None

        if use_reranker:
            from sentence_transformers import CrossEncoder

            self._reranker = CrossEncoder(
                "cross-encoder/ms-marco-MiniLM-L-6-v2"
            )

    def retrieve(
        self,
        query: str,
        filter_metadata: Optional[dict] = None,
    ) -> List[dict]:

        query_vec = self.embedder.embed_query(query)

        fetch_k = self.top_k * 3 if self.use_reranker else self.top_k

        hits = self.vectordb.similarity_search(
            query_embedding=query_vec,
            top_k=fetch_k,
            filter_metadata=filter_metadata,
        )

        if self.use_reranker and hits:

            pairs = [(query, h["text"]) for h in hits]

            scores = self._reranker.predict(pairs)

            for h, s in zip(hits, scores):
                h["score"] = float(s)

            hits.sort(
                key=lambda x: x["score"],
                reverse=True,
            )

            hits = hits[: self.top_k]

        results = []

        for h in hits:

            if h["score"] < self.min_score:
                continue

            results.append(
                {
                    "text": h["text"],
                    "score": h["score"],
                    "document": h["metadata"].get("source"),
                    "section": h["metadata"].get("chunk_index"),
                    "metadata": h["metadata"],
                }
            )

        return results

    def format_context(
        self,
        chunks: List[dict],
    ) -> str:

        if not chunks:
            return "No relevant context found."

        blocks = []

        for i, c in enumerate(chunks, start=1):

            blocks.append(
                f"[Source {i}: {c['document']} | relevance={c['score']:.2f}]\n"
                f"{c['text']}"
            )

        return "\n\n".join(blocks)


_embedder = EmbeddingModel(provider="local")
_vectordb = VectorDB(persist_path="data/vector_store")
_retriever = Retriever(_embedder, _vectordb)


def retrieve(query: str, top_k: int = 5):
    _retriever.top_k = top_k
    return _retriever.retrieve(query)


if __name__ == "__main__":

    results = retrieve(
        "What is the refund window?",
        top_k=3,
    )

    print(_retriever.format_context(results))
def retrieve(query: str, top_k: int = 5):
    embedder = EmbeddingModel(provider="local")
    db = VectorDB(persist_path="./data/vector_store")

    retriever = Retriever(
        embedder=embedder,
        vectordb=db,
        top_k=top_k,
        min_score=0.2,
    )

    return retriever.retrieve(query)