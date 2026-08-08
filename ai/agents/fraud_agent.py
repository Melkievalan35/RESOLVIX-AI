"""
fraud_agent.py
Scores a complaint for potential fraud/abuse (e.g. serial-refund abuse,
mismatched or reused evidence, behavioral anomalies) using the
ai/fraud modules. Produces a 0-1 fraud_score plus explainable flags.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base_agent import AgentResult, BaseAgent, ComplaintContext

try:
    from ai.fraud.anomaly_detection import detect_anomalies
    from ai.fraud.fraud_score import compute_fraud_score
    from ai.fraud.behavioral_analysis import analyze_customer_behavior
except ImportError:  # pragma: no cover
    detect_anomalies = None
    compute_fraud_score = None
    analyze_customer_behavior = None


FRAUD_FLAG_THRESHOLD = 0.65


class FraudAgent(BaseAgent):
    name = "fraud_agent"

    def process(self, context: ComplaintContext) -> AgentResult:
        behavior = self._get_behavior_profile(context.customer_id)
        anomalies = self._get_anomalies(context)
        score = self._get_score(context, behavior, anomalies)

        flags: List[str] = []
        if behavior.get("refund_count_last_90_days", 0) >= 3:
            flags.append("frequent_refund_requests")
        if behavior.get("account_age_days", 999) < 7:
            flags.append("new_account")
        if anomalies.get("image_reuse_detected"):
            flags.append("duplicate_or_reused_evidence")
        if anomalies.get("text_similarity_to_prior_claims", 0) > 0.85:
            flags.append("near_duplicate_complaint_text")

        context.fraud_score = score
        context.fraud_flags = flags

        return AgentResult(
            agent_name=self.name,
            success=True,
            data={"fraud_score": score, "flags": flags, "behavior": behavior, "anomalies": anomalies},
            confidence=0.8 if compute_fraud_score else 0.4,
            reasoning=(
                f"Fraud score {score:.2f} derived from behavioral profile and anomaly checks. "
                f"Flags raised: {flags or 'none'}."
            ),
        )

    def _get_behavior_profile(self, customer_id: str) -> Dict[str, Any]:
        if analyze_customer_behavior is None:
            return {"refund_count_last_90_days": 0, "account_age_days": 365}
        return analyze_customer_behavior(customer_id)

    def _get_anomalies(self, context: ComplaintContext) -> Dict[str, Any]:
        if detect_anomalies is None:
            return {}
        return detect_anomalies(
            complaint_text=context.raw_text,
            attachments=context.attachments,
            customer_id=context.customer_id,
        )

    def _get_score(
        self, context: ComplaintContext, behavior: Dict[str, Any], anomalies: Dict[str, Any]
    ) -> float:
        if compute_fraud_score is not None:
            return float(compute_fraud_score(behavior=behavior, anomalies=anomalies))

        # Deterministic fallback heuristic if the ML scorer isn't wired up.
        score = 0.1
        score += 0.15 * min(behavior.get("refund_count_last_90_days", 0), 4)
        score += 0.2 if behavior.get("account_age_days", 999) < 7 else 0.0
        score += 0.3 if anomalies.get("image_reuse_detected") else 0.0
        score += 0.2 * anomalies.get("text_similarity_to_prior_claims", 0.0)
        return round(min(score, 1.0), 2)

    def is_high_risk(self, context: ComplaintContext) -> bool:
        return (context.fraud_score or 0.0) >= FRAUD_FLAG_THRESHOLD
