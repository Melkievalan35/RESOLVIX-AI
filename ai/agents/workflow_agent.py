"""
workflow_agent.py
Drives the complaint through its lifecycle state machine and decides
which downstream services (notifications, ticketing, reports) need to
fire for the current state transition.

States: received -> triaged -> evidence_review -> policy_check ->
        fraud_check -> resolved | escalated -> closed
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base_agent import AgentResult, BaseAgent, ComplaintContext


VALID_TRANSITIONS: Dict[str, List[str]] = {
    "received": ["triaged"],
    "triaged": ["evidence_review", "policy_check"],
    "evidence_review": ["policy_check"],
    "policy_check": ["fraud_check"],
    "fraud_check": ["resolved", "escalated"],
    "resolved": ["closed"],
    "escalated": ["closed", "resolved"],
    "closed": [],
}

NOTIFICATION_MAP: Dict[str, str] = {
    "triaged": "complaint_received_confirmation",
    "resolved": "resolution_notice",
    "escalated": "escalation_notice",
    "closed": "case_closed_survey",
}


class WorkflowAgent(BaseAgent):
    name = "workflow_agent"

    def process(self, context: ComplaintContext) -> AgentResult:
        next_state = self._determine_next_state(context)
        valid = next_state in VALID_TRANSITIONS.get(context.workflow_state, [])

        if not valid:
            return AgentResult(
                agent_name=self.name,
                success=False,
                data={"attempted_transition": f"{context.workflow_state} -> {next_state}"},
                confidence=0.0,
                error="invalid_state_transition",
                reasoning=(
                    f"Transition from '{context.workflow_state}' to '{next_state}' is not "
                    "permitted by the workflow state machine."
                ),
            )

        previous_state = context.workflow_state
        context.workflow_state = next_state
        notification = NOTIFICATION_MAP.get(next_state)

        return AgentResult(
            agent_name=self.name,
            success=True,
            data={
                "previous_state": previous_state,
                "new_state": next_state,
                "notification_to_send": notification,
            },
            confidence=1.0,
            reasoning=f"Advanced workflow state: '{previous_state}' -> '{next_state}'.",
        )

    def _determine_next_state(self, context: ComplaintContext) -> str:
        state = context.workflow_state
        if state == "received":
            return "triaged"
        if state == "triaged":
            return "evidence_review" if context.attachments else "policy_check"
        if state == "evidence_review":
            return "policy_check"
        if state == "policy_check":
            return "fraud_check"
        if state == "fraud_check":
            return "escalated" if context.escalated else "resolved"
        if state == "resolved":
            return "closed"
        if state == "escalated":
            return "closed" if context.resolution else "escalated"
        return state
