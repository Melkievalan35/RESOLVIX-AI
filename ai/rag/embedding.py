"""
embedding.py
------------
Wraps an embedding model so the rest of the pipeline (vectordb, retriever)
never has to care which provider is behind it. Defaults to a local
sentence-transformers model (free, no API key, works offline -- good
for a hackathon demo with unreliable wifi). Swap `provider="openai"` or
`provider="anthropic-voyage"` for production-grade embeddings.

Used by: ai/rag/embedding.py
"""

from typing import List
import os


class EmbeddingModel:
    def __init__(self, provider: str = "local", model_name: str = None):
        self.provider = provider

        if provider == "local":
            # all-MiniLM-L6-v2: 384-dim, fast, runs on CPU -- ideal for a 24hr hackathon
            from sentence_transformers import SentenceTransformer
            self.model_name = model_name or "sentence-transformers/all-MiniLM-L6-v2"
            self._model = SentenceTransformer(self.model_name)
            self.dimension = self._model.get_sentence_embedding_dimension()

        elif provider == "openai":
            from openai import OpenAI
            self.model_name = model_name or "text-embedding-3-small"
            self._client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
            self.dimension = 1536

        elif provider == "voyage":
            # Voyage AI embeddings pair naturally with Claude-based generation
            import voyageai
            self.model_name = model_name or "voyage-3"
            self._client = voyageai.Client(api_key=os.environ.get("VOYAGE_API_KEY"))
            self.dimension = 1024

        else:
            raise ValueError(f"Unknown embedding provider: {provider}")

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        if self.provider == "local":
            return self._model.encode(texts, normalize_embeddings=True).tolist()

        if self.provider == "openai":
            resp = self._client.embeddings.create(model=self.model_name, input=texts)
            return [d.embedding for d in resp.data]

        if self.provider == "voyage":
            resp = self._client.embed(texts, model=self.model_name, input_type="document")
            return resp.embeddings

    def embed_query(self, query: str) -> List[float]:
        if self.provider == "voyage":
            resp = self._client.embed([query], model=self.model_name, input_type="query")
            return resp.embeddings[0]
        return self.embed_texts([query])[0]


if __name__ == "__main__":
    embedder = EmbeddingModel(provider="local")
    vecs = embedder.embed_texts(["Refund policy allows returns within 30 days."])
    print(f"Embedding dimension: {len(vecs[0])}")
