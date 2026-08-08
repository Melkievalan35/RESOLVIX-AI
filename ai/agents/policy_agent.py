"""
policy_agent.py
RAG-driven agent that grounds a complaint in the company's actual policy
documents (Refund Policy, Warranty Policy, SLA, FAQ) so downstream
resolutions are policy-compliant and explainable.

Pipeline: retrieve -> rerank -> generate a structured policy verdict.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .base_agent import AgentResult, BaseAgent, ComplaintContext

try:
    from ai.rag.retriever import retrieve
    print("✅ Retriever imported")
except Exception as e:
    print("❌ Retriever Import Error:", e)
    retrieve = None

try:
    from ai.rag.generator import generate_answer
    print("✅ Generator imported")
except Exception as e:
    print("❌ Generator Import Error:", e)
    generate_answer = None


class PolicyAgent(BaseAgent):
    name = "policy_agent"

    def __init__(self, llm_client: Any = None, config: Optional[Dict[str, Any]] = None, top_k: int = 5):
        super().__init__(llm_client, config)
        self.top_k = top_k

    def process(self, context: ComplaintContext) -> AgentResult:
        query = self._build_query(context)

        if retrieve is None:
            return AgentResult(
                agent_name=self.name,
                success=False,
                data={},
                confidence=0.0,
                error="RAG retriever not available",
                reasoning="ai.rag.retriever could not be imported; cannot ground policy verdict.",
            )

        candidates = retrieve(query, top_k=self.top_k)
        top_chunks = candidates[: self.top_k]

        verdict = self._generate_verdict(query, top_chunks, context)

        context.policy_findings = {
            "query": query,
            "sources": [
                {"document": c.get("document"), "section": c.get("section"), "score": c.get("score")}
                for c in top_chunks
            ],
            "verdict": verdict,
        }

        confidence = self._estimate_confidence(top_chunks)

        return AgentResult(
            agent_name=self.name,
            success=True,
            data=context.policy_findings,
            confidence=confidence,
            reasoning=(
                f"Retrieved {len(top_chunks)} policy chunk(s); verdict "
                f"'{verdict.get('eligibility', 'unknown')}' with confidence {confidence:.2f}."
            ),
        )

    def _build_query(self, context: ComplaintContext) -> str:
        parts = [context.category or "", context.raw_text or ""]
        if context.evidence_findings.get("damage_confirmed"):
            parts.append("physical damage confirmed by photo evidence")
        return " | ".join(p for p in parts if p)

    def _generate_verdict(
        self, query: str, chunks: List[Dict[str, Any]], context: ComplaintContext
    ) -> Dict[str, Any]:
        """Combine retrieved chunks into a structured, citable verdict."""
        if generate_answer is not None:
            try:
                raw = generate_answer(query=query, context_chunks=chunks)
                parsed = json.loads(raw) if isinstance(raw, str) else raw
                if isinstance(parsed, dict):
                    return parsed
            except Exception:  # noqa: BLE001
                pass

        # Deterministic fallback if generation is unavailable/unparseable.
        eligible = any("refund" in (c.get("text", "").lower()) for c in chunks)
        return {
            "eligibility": "likely_eligible" if eligible else "needs_review",
            "applicable_policy": chunks[0].get("document") if chunks else None,
            "conditions": [c.get("section") for c in chunks if c.get("section")],
            "notes": "Fallback rule-based verdict; LLM generation unavailable.",
        }

    def _estimate_confidence(self, chunks: List[Dict[str, Any]]) -> float:
        if not chunks:
            return 0.1
        scores = [c.get("score", 0.5) for c in chunks]
        return round(sum(scores) / len(scores), 2)
