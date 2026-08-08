"""
confidence_score.py
--------------------
Computes a calibrated confidence score for every AI-driven decision made
inside the Resolvix-AI pipeline (e.g. "approve refund", "flag as fraud",
"escalate to human agent").

Design goals
============
1. Combine signals from multiple agents/models instead of trusting a single
   LLM's self-reported certainty (LLMs are notoriously overconfident).
2. Produce a 0-100 score plus a human-readable confidence band
   (High / Medium / Low) that the frontend and audit log can display.
3. Be fully explainable: every component that contributed to the score is
   returned alongside the final number, not hidden inside a black box.

This module has no external dependencies beyond the standard library so it
can be unit-tested in isolation from the LLM/vector-DB layer.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class ConfidenceBand(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


@dataclass
class SignalContribution:
    """A single input that fed into the final confidence score."""
    name: str
    raw_value: float          # 0.0 - 1.0
    weight: float             # relative importance, weights should sum to 1.0
    weighted_value: float = field(init=False)
    rationale: str = ""

    def __post_init__(self):
        self.weighted_value = round(self.raw_value * self.weight, 4)


@dataclass
class ConfidenceResult:
    score: float                       # final 0-100 score
    band: ConfidenceBand
    signals: List[SignalContribution]
    requires_human_review: bool
    summary: str

    def to_dict(self) -> Dict:
        return {
            "score": self.score,
            "band": self.band.value,
            "requires_human_review": self.requires_human_review,
            "summary": self.summary,
            "signals": [
                {
                    "name": s.name,
                    "raw_value": s.raw_value,
                    "weight": s.weight,
                    "weighted_value": s.weighted_value,
                    "rationale": s.rationale,
                }
                for s in self.signals
            ],
        }


# Default weighting scheme. Tunable per use-case (refund vs. warranty vs.
# fraud) by passing a custom `weights` dict into ConfidenceScorer.
DEFAULT_WEIGHTS = {
    "retrieval_relevance": 0.25,   # how well the RAG retriever matched policy docs
    "llm_self_reported": 0.15,     # LLM's own certainty (down-weighted deliberately)
    "agent_agreement": 0.25,       # how many agents in the multi-agent pipeline agree
    "fraud_risk_inverse": 0.15,    # (1 - fraud_score); higher fraud risk lowers confidence
    "evidence_completeness": 0.20, # were all required documents/images provided?
}

# Thresholds for routing decisions
HUMAN_REVIEW_THRESHOLD = 60.0
HIGH_BAND_THRESHOLD = 80.0
MEDIUM_BAND_THRESHOLD = 60.0


class ConfidenceScorer:
    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = weights or DEFAULT_WEIGHTS
        total = sum(self.weights.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"Confidence weights must sum to 1.0, got {total}")

    def score(
        self,
        retrieval_relevance: float,
        llm_self_reported: float,
        agent_agreement: float,
        fraud_score: float,
        evidence_completeness: float,
        rationales: Optional[Dict[str, str]] = None,
    ) -> ConfidenceResult:
        """
        All raw inputs are expected in the 0.0-1.0 range.

        fraud_score: 0.0 = no fraud risk, 1.0 = certain fraud. It is inverted
        internally because *lower* fraud risk should *raise* confidence.
        """
        rationales = rationales or {}
        raw_values = {
            "retrieval_relevance": retrieval_relevance,
            "llm_self_reported": llm_self_reported,
            "agent_agreement": agent_agreement,
            "fraud_risk_inverse": 1.0 - fraud_score,
            "evidence_completeness": evidence_completeness,
        }

        signals = [
            SignalContribution(
                name=name,
                raw_value=round(value, 4),
                weight=self.weights[name],
                rationale=rationales.get(name, self._default_rationale(name, value)),
            )
            for name, value in raw_values.items()
        ]

        final_score = round(sum(s.weighted_value for s in signals) * 100, 2)
        band = self._band_for(final_score)
        requires_review = final_score < HUMAN_REVIEW_THRESHOLD

        return ConfidenceResult(
            score=final_score,
            band=band,
            signals=signals,
            requires_human_review=requires_review,
            summary=self._build_summary(final_score, band, signals, requires_review),
        )

    @staticmethod
    def _band_for(score: float) -> ConfidenceBand:
        if score >= HIGH_BAND_THRESHOLD:
            return ConfidenceBand.HIGH
        if score >= MEDIUM_BAND_THRESHOLD:
            return ConfidenceBand.MEDIUM
        return ConfidenceBand.LOW

    @staticmethod
    def _default_rationale(name: str, value: float) -> str:
        readable = {
            "retrieval_relevance": "Relevance of retrieved policy/knowledge-base chunks",
            "llm_self_reported": "LLM's own certainty in its generated answer",
            "agent_agreement": "Agreement level across Policy, Fraud, and Resolution agents",
            "fraud_risk_inverse": "Inverse of the fraud model's risk score",
            "evidence_completeness": "Proportion of required evidence (images/invoices) supplied",
        }.get(name, name)
        return f"{readable}: {value:.2f}"

    @staticmethod
    def _build_summary(
        score: float,
        band: ConfidenceBand,
        signals: List[SignalContribution],
        requires_review: bool,
    ) -> str:
        weakest = min(signals, key=lambda s: s.weighted_value)
        strongest = max(signals, key=lambda s: s.weighted_value)
        parts = [
            f"Confidence {score}/100 ({band.value}).",
            f"Strongest signal: {strongest.name} ({strongest.raw_value:.2f}).",
            f"Weakest signal: {weakest.name} ({weakest.raw_value:.2f}).",
        ]
        if requires_review:
            parts.append("Routed to human review because score is below threshold.")
        return " ".join(parts)


if __name__ == "__main__":
    scorer = ConfidenceScorer()
    result = scorer.score(
        retrieval_relevance=0.91,
        llm_self_reported=0.88,
        agent_agreement=0.75,
        fraud_score=0.05,
        evidence_completeness=1.0,
    )
    import json
    print(json.dumps(result.to_dict(), indent=2))
