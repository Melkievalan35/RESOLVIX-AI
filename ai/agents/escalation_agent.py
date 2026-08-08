"""
escalation_agent.py
Decides whether a complaint needs to be handed off to a human agent, and
if so, to which team/priority queue. Considers fraud risk, resolution
confidence, customer sentiment/urgency, and complaint value.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .base_agent import AgentResult, BaseAgent, ComplaintContext

HIGH_FRAUD_THRESHOLD = 0.5
LOW_RESOLUTION_CONFIDENCE = 0.5

TEAM_ROUTING = {
    "deny_pending_investigation": "fraud_investigation_team",
    "manual_review": "general_support_team",
    "request_additional_evidence": "general_support_team",
}


class EscalationAgent(BaseAgent):
    name = "escalation_agent"

    def process(self, context: ComplaintContext) -> AgentResult:
        resolution = context.resolution or {}
        decision = resolution.get("decision")
        fraud_score = context.fraud_score or 0.0
        resolution_confidence = self._resolution_confidence(context)

        should_escalate, reason = self._should_escalate(
            decision=decision,
            fraud_score=fraud_score,
            resolution_confidence=resolution_confidence,
            requires_human=resolution.get("requires_human_review", False),
        )

        team = TEAM_ROUTING.get(decision, "general_support_team") if should_escalate else None
        priority = self._priority(fraud_score, context)

        context.escalated = should_escalate
        context.escalation_reason = reason if should_escalate else None

        return AgentResult(
            agent_name=self.name,
            success=True,
            data={
                "escalated": should_escalate,
                "team": team,
                "priority": priority,
                "reason": reason,
            },
            confidence=0.85,
            reasoning=reason,
        )

    def _resolution_confidence(self, context: ComplaintContext) -> float:
        for entry in reversed(context.agent_trace):
            if entry["agent_name"] == "resolution_agent":
                return entry["confidence"]
        return 0.5

    def _should_escalate(
        self, decision: Optional[str], fraud_score: float, resolution_confidence: float, requires_human: bool
    ) -> (bool, str):
        if requires_human:
            return True, f"Resolution agent flagged '{decision}' as requiring human review."
        if fraud_score >= HIGH_FRAUD_THRESHOLD:
            return True, f"Fraud score {fraud_score:.2f} meets the human-review threshold."
        if resolution_confidence < LOW_RESOLUTION_CONFIDENCE:
            return True, f"Resolution confidence {resolution_confidence:.2f} is below the auto-resolve bar."
        return False, "Case meets criteria for fully automated resolution."

    def _priority(self, fraud_score: float, context: ComplaintContext) -> str:
        if fraud_score >= HIGH_FRAUD_THRESHOLD or context.priority == "high":
            return "high"
        if context.priority == "medium":
            return "medium"
        return "low"
