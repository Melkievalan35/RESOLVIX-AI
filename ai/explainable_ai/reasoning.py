"""
reasoning.py
------------
Builds a structured, step-by-step reasoning trace for every decision the
multi-agent pipeline makes. This is what powers the "Why did the AI decide
this?" panel in the customer/admin portals, and what judges will click on
during the live demo to prove the system isn't a black box.

Two things are produced for every decision:
1. A machine-readable `ReasoningTrace` (list of ReasoningStep objects) that
   the frontend can render as a timeline / stepper component.
2. A natural-language explanation string suitable for showing directly to
   a non-technical customer.

The trace is agent-agnostic: any agent (Policy, Fraud, Resolution, etc.)
can log a step via `ReasoningTrace.add_step(...)`, so the final trace shows
the full multi-agent journey, not just the final agent's output.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional


@dataclass
class ReasoningStep:
    agent: str                     # e.g. "PolicyAgent", "FraudAgent"
    action: str                    # e.g. "Retrieved refund policy clause 4.2"
    input_summary: str             # short description of what the agent received
    output_summary: str            # short description of what the agent produced
    evidence_refs: List[str] = field(default_factory=list)  # doc IDs, image IDs, etc.
    confidence: Optional[float] = None   # 0.0-1.0, this step's local confidence
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict:
        return {
            "agent": self.agent,
            "action": self.action,
            "input_summary": self.input_summary,
            "output_summary": self.output_summary,
            "evidence_refs": self.evidence_refs,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
        }


class ReasoningTrace:
    """Accumulates ReasoningSteps across the multi-agent workflow for a
    single complaint/case, then renders them for humans."""

    def __init__(self, case_id: str):
        self.case_id = case_id
        self.steps: List[ReasoningStep] = []

    def add_step(
        self,
        agent: str,
        action: str,
        input_summary: str,
        output_summary: str,
        evidence_refs: Optional[List[str]] = None,
        confidence: Optional[float] = None,
    ) -> ReasoningStep:
        step = ReasoningStep(
            agent=agent,
            action=action,
            input_summary=input_summary,
            output_summary=output_summary,
            evidence_refs=evidence_refs or [],
            confidence=confidence,
        )
        self.steps.append(step)
        return step

    def to_dict(self) -> Dict:
        return {
            "case_id": self.case_id,
            "step_count": len(self.steps),
            "steps": [s.to_dict() for s in self.steps],
        }

    def to_customer_explanation(self) -> str:
        """Plain-language explanation, safe to show directly to an end user."""
        if not self.steps:
            return "No decision has been made yet for this case."

        lines = [f"Here's how we reached a decision on case {self.case_id}:"]
        for i, step in enumerate(self.steps, start=1):
            lines.append(f"{i}. {step.agent}: {step.output_summary}")
        return "\n".join(lines)

    def to_audit_narrative(self) -> str:
        """More technical narrative for internal audit logs / admin dashboard."""
        if not self.steps:
            return f"No reasoning steps recorded for case {self.case_id}."

        lines = [f"Reasoning trace for case {self.case_id} ({len(self.steps)} steps):"]
        for step in self.steps:
            conf = f", confidence={step.confidence:.2f}" if step.confidence is not None else ""
            evidence = f", evidence={step.evidence_refs}" if step.evidence_refs else ""
            lines.append(
                f"  [{step.timestamp}] {step.agent} -> {step.action}"
                f" | input: {step.input_summary} | output: {step.output_summary}"
                f"{conf}{evidence}"
            )
        return "\n".join(lines)


def build_sample_trace() -> ReasoningTrace:
    """Example trace matching the Resolvix-AI agent pipeline. Useful for
    demos, tests, and for wiring up the frontend before the real agents
    are fully connected."""
    trace = ReasoningTrace(case_id="CMP-10231")

    trace.add_step(
        agent="CustomerAgent",
        action="Parsed complaint text and classified intent",
        input_summary="Customer message: 'My product arrived damaged, I want a refund.'",
        output_summary="Classified as: damaged_item_refund_request",
        confidence=0.94,
    )
    trace.add_step(
        agent="EvidenceAgent",
        action="Analyzed uploaded photos and invoice via vision + OCR models",
        input_summary="2 images, 1 invoice PDF",
        output_summary="Damage confirmed in product image; invoice matches order ID",
        evidence_refs=["img_001.jpg", "img_002.jpg", "invoice_4471.pdf"],
        confidence=0.89,
    )
    trace.add_step(
        agent="PolicyAgent",
        action="Retrieved applicable refund policy via RAG",
        input_summary="Query: 'refund policy for damaged items within 30 days'",
        output_summary="Matched Refund Policy clause 4.2: full refund if damage reported within 30 days",
        evidence_refs=["Refund_Policy.pdf#clause-4.2"],
        confidence=0.91,
    )
    trace.add_step(
        agent="FraudAgent",
        action="Scored case for anomalous refund patterns",
        input_summary="Customer history: 1 prior refund in 12 months",
        output_summary="Low fraud risk (score 0.05)",
        confidence=0.95,
    )
    trace.add_step(
        agent="ResolutionAgent",
        action="Combined evidence, policy, and fraud signals to decide outcome",
        input_summary="Evidence confirmed, policy applies, fraud risk low",
        output_summary="Decision: Approve full refund of $49.99",
        confidence=0.90,
    )
    return trace


if __name__ == "__main__":
    demo_trace = build_sample_trace()
    print(demo_trace.to_customer_explanation())
    print("\n---\n")
    print(demo_trace.to_audit_narrative())
