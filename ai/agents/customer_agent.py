"""
customer_agent.py
Entry-point agent for the complaint pipeline.

Responsibilities:
  - Parse the raw customer complaint text
  - Extract intent, category, and key entities (order id, product, dates)
  - Run lightweight sentiment/urgency detection so downstream agents
    (Workflow, Escalation) have an initial signal before the dedicated
    sentiment module runs
  - Produce a clarifying question if the complaint is too vague to route
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from .base_agent import AgentResult, BaseAgent, ComplaintContext

CATEGORY_KEYWORDS = {
    "refund": ["refund", "money back", "reimburse"],
    "damaged_product": ["damaged", "broken", "defective", "cracked"],
    "delivery_delay": ["late", "delayed", "not delivered", "still waiting"],
    "billing_issue": ["overcharged", "billing", "invoice", "charged twice"],
    "service_quality": ["rude", "poor service", "unhelpful"],
    "warranty_claim": ["warranty", "under warranty", "repair"],
}

URGENCY_KEYWORDS = ["urgent", "immediately", "asap", "furious", "unacceptable", "legal action"]

ORDER_ID_PATTERN = re.compile(r"\b(?:order|invoice|ref)[\s#:]*([A-Z0-9\-]{5,15})\b", re.IGNORECASE)


class CustomerAgent(BaseAgent):
    name = "customer_agent"

    def process(self, context: ComplaintContext) -> AgentResult:
        text = context.raw_text or ""
        category, cat_confidence = self._classify_category(text)
        entities = self._extract_entities(text)
        urgency = self._detect_urgency(text)

        # Optionally refine with an LLM call for a natural-language summary
        # and a structured intent object if an llm client is configured.
        llm_summary = None
        if self.llm is not None:
            llm_summary = self._llm_extract(text)
            if llm_summary and llm_summary.get("category"):
                category = llm_summary["category"]
                cat_confidence = max(cat_confidence, 0.75)

        context.intent = (llm_summary or {}).get("intent", category)
        context.category = category

        needs_clarification = cat_confidence < 0.4 and not entities.get("order_id")

        data = {
            "category": category,
            "entities": entities,
            "urgency": urgency,
            "needs_clarification": needs_clarification,
            "summary": (llm_summary or {}).get("summary", text[:200]),
        }

        return AgentResult(
            agent_name=self.name,
            success=True,
            data=data,
            confidence=cat_confidence,
            reasoning=(
                f"Classified complaint as '{category}' (confidence={cat_confidence:.2f}) "
                f"based on keyword matching{' + LLM refinement' if llm_summary else ''}."
            ),
        )

    def _classify_category(self, text: str) -> (str, float):
        text_lower = text.lower()
        best_category, best_hits = "general_inquiry", 0
        for category, keywords in CATEGORY_KEYWORDS.items():
            hits = sum(1 for kw in keywords if kw in text_lower)
            if hits > best_hits:
                best_category, best_hits = category, hits
        confidence = min(0.3 + 0.2 * best_hits, 0.9) if best_hits else 0.2
        return best_category, confidence

    def _extract_entities(self, text: str) -> Dict[str, Optional[str]]:
        match = ORDER_ID_PATTERN.search(text)
        return {"order_id": match.group(1) if match else None}

    def _detect_urgency(self, text: str) -> bool:
        text_lower = text.lower()
        return any(kw in text_lower for kw in URGENCY_KEYWORDS)

    def _llm_extract(self, text: str) -> Optional[Dict[str, Any]]:
        """Ask the LLM for a structured intent object. Expects the llm_client
        to expose a `.complete(prompt: str) -> str` method returning JSON."""
        prompt = (
            "Extract the customer's complaint intent as strict JSON with keys "
            '"intent", "category", "summary" (<=200 chars). '
            f"Complaint:\n{text}\nRespond with JSON only."
        )
        try:
            raw = self.llm.complete(prompt)
            return json.loads(raw)
        except Exception:  # noqa: BLE001
            return None
