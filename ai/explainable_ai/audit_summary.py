"""
audit_summary.py
-----------------
Combines `ConfidenceResult` (confidence_score.py) and `ReasoningTrace`
(reasoning.py) into one immutable audit record per case. This is the object
that gets persisted to the audit_logs table and shown on the admin
dashboard's "Audit Logs" screen — it is the single source of truth for
"what did the AI do, and why should we trust it."

Also exposes a JSON export helper, since judges and enterprise buyers will
often ask "can you show me the raw audit trail," and having it export
cleanly is an easy credibility win in a demo.
"""

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from confidence_score import ConfidenceResult
from reasoning import ReasoningTrace


@dataclass
class AuditSummary:
    case_id: str
    decision: str                      # e.g. "Refund Approved", "Escalated to Human"
    decided_by: str                    # e.g. "ResolutionAgent" or "Human:agent_id_42"
    confidence: ConfidenceResult
    reasoning: ReasoningTrace
    policy_citations: List[str] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)   # e.g. "human_review_required"
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict:
        return {
            "case_id": self.case_id,
            "decision": self.decision,
            "decided_by": self.decided_by,
            "created_at": self.created_at,
            "confidence": self.confidence.to_dict(),
            "reasoning": self.reasoning.to_dict(),
            "policy_citations": self.policy_citations,
            "flags": self.flags,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def to_dashboard_row(self) -> Dict:
        """Compact representation for the Admin Dashboard's audit log table."""
        return {
            "case_id": self.case_id,
            "decision": self.decision,
            "confidence_score": self.confidence.score,
            "confidence_band": self.confidence.band.value,
            "decided_by": self.decided_by,
            "flags": ", ".join(self.flags) if self.flags else "-",
            "created_at": self.created_at,
        }


class AuditSummaryBuilder:
    """Convenience builder that wires confidence + reasoning together and
    applies standard business rules (e.g. auto-flagging low-confidence
    cases for human review)."""

    @staticmethod
    def build(
        case_id: str,
        decision: str,
        decided_by: str,
        confidence: ConfidenceResult,
        reasoning: ReasoningTrace,
        policy_citations: Optional[List[str]] = None,
    ) -> AuditSummary:
        flags: List[str] = []
        if confidence.requires_human_review:
            flags.append("human_review_required")
        if confidence.band.value == "Low":
            flags.append("low_confidence")
        if any("fraud" in step.action.lower() for step in reasoning.steps
               if "high" in step.output_summary.lower()):
            flags.append("fraud_signal_present")

        return AuditSummary(
            case_id=case_id,
            decision=decision,
            decided_by=decided_by,
            confidence=confidence,
            reasoning=reasoning,
            policy_citations=policy_citations or [],
            flags=flags,
        )


if __name__ == "__main__":
    from confidence_score import ConfidenceScorer
    from reasoning import build_sample_trace

    scorer = ConfidenceScorer()
    confidence = scorer.score(
        retrieval_relevance=0.91,
        llm_self_reported=0.88,
        agent_agreement=0.75,
        fraud_score=0.05,
        evidence_completeness=1.0,
    )
    trace = build_sample_trace()

    audit = AuditSummaryBuilder.build(
        case_id="CMP-10231",
        decision="Refund Approved ($49.99)",
        decided_by="ResolutionAgent",
        confidence=confidence,
        reasoning=trace,
        policy_citations=["Refund_Policy.pdf#clause-4.2"],
    )

    print(audit.to_json())
    print("\n--- Dashboard row ---")
    print(audit.to_dashboard_row())
