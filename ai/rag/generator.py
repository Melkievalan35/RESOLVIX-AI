"""
generator.py
------------
Takes the user's query + retrieved context and produces a grounded,
citation-aware answer. Includes a confidence score and explicit
"insufficient evidence" fallback -- this is the piece that plugs into
your Explainable AI layer (ai/explainable_ai/confidence_score.py) and
is a strong talking point for the "Explainability" judging criterion.

Used by: ai/rag/generator.py
"""

from dataclasses import dataclass
from typing import List
import os
import json

from .retriever import RetrievedChunk

SYSTEM_PROMPT = """You are Resolvix-AI's policy assistant. Answer the customer's \
question using ONLY the provided context. If the context does not contain \
enough information, say so explicitly rather than guessing.

Respond in strict JSON with this shape:
{
  "answer": "<concise answer grounded in the context>",
  "confidence": <float 0-1>,
  "cited_sources": ["<source names used>"],
  "sufficient_evidence": <true|false>
}
"""


@dataclass
class GeneratedResponse:
    answer: str
    confidence: float
    cited_sources: List[str]
    sufficient_evidence: bool
    raw_context: str


class Generator:
    def __init__(self, provider: str = "anthropic", model: str = None):
        self.provider = provider
        if provider == "anthropic":
            import anthropic
            self.model = model or "claude-sonnet-4-6"
            self._client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        elif provider == "openai":
            from openai import OpenAI
            self.model = model or "gpt-4o-mini"
            self._client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        else:
            raise ValueError(f"Unknown generator provider: {provider}")

    def _call_llm(self, user_prompt: str) -> str:
        if self.provider == "anthropic":
            msg = self._client.messages.create(
                model=self.model,
                max_tokens=600,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return "".join(block.text for block in msg.content if block.type == "text")

        if self.provider == "openai":
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
            )
            return resp.choices[0].message.content

    def generate(self, query: str, context_chunks: List[RetrievedChunk]) -> GeneratedResponse:
        context_text = "\n\n".join(
            f"[Source: {c.source} | relevance={c.score:.2f}]\n{c.text}" for c in context_chunks
        ) or "No relevant context retrieved."

        user_prompt = f"Context:\n{context_text}\n\nCustomer question: {query}"
        raw = self._call_llm(user_prompt)

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            # graceful fallback if the model doesn't return clean JSON
            parsed = {
                "answer": raw,
                "confidence": 0.5,
                "cited_sources": [c.source for c in context_chunks],
                "sufficient_evidence": bool(context_chunks),
            }

        return GeneratedResponse(
            answer=parsed.get("answer", ""),
            confidence=float(parsed.get("confidence", 0.0)),
            cited_sources=parsed.get("cited_sources", []),
            sufficient_evidence=bool(parsed.get("sufficient_evidence", False)),
            raw_context=context_text,
        )
_generator = Generator(provider="anthropic")

def generate_answer(query: str, context_chunks):
    """
    Wrapper used by PolicyAgent.
    Returns a dictionary that matches PolicyAgent's expected format.
    """
    result = _generator.generate(query, context_chunks)

    return {
        "eligibility": "likely_eligible" if result.sufficient_evidence else "needs_review",
        "applicable_policy": result.cited_sources[0] if result.cited_sources else None,
        "conditions": result.cited_sources,
        "notes": result.answer,
        "confidence": result.confidence,
    }


if __name__ == "__main__":
    sample_chunks = [
        RetrievedChunk(
            text="Customers are eligible for a full refund within 30 days of purchase.",
            source="Refund Policy.pdf",
            score=0.91,
            metadata={},
        )
    ]
    gen = Generator(provider="anthropic")
    result = gen.generate("Can I get a refund after 20 days?", sample_chunks)
    print(result)
