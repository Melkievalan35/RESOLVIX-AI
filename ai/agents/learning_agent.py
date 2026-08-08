"""
learning_agent.py
Closes the loop: records the final outcome of each complaint (resolution
taken, whether it was appealed/overturned, human feedback, CSAT) so the
system can be evaluated and periodically retrained/fine-tuned. This
agent doesn't run inline with every complaint's critical path — it's
invoked after resolution/closure to log structured training data.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, Optional

from .base_agent import AgentResult, BaseAgent, ComplaintContext


class LearningAgent(BaseAgent):
    name = "learning_agent"

    def __init__(
        self,
        llm_client: Any = None,
        config: Optional[Dict[str, Any]] = None,
        feedback_store_path: str = "storage/logs/learning_feedback.jsonl",
    ):
        super().__init__(llm_client, config)
        self.feedback_store_path = feedback_store_path

    def process(self, context: ComplaintContext) -> AgentResult:
        record = self._build_record(context)
        written = self._persist(record)

        return AgentResult(
            agent_name=self.name,
            success=written,
            data={"record_id": record["complaint_id"], "stored": written},
            confidence=1.0 if written else 0.0,
            reasoning=(
                "Logged complaint outcome for future model evaluation/retraining."
                if written
                else "Failed to persist learning record; see error."
            ),
            error=None if written else "could_not_write_feedback_store",
        )

    def record_human_feedback(
        self, context: ComplaintContext, agent_decision_correct: bool, human_notes: str = ""
    ) -> AgentResult:
        """Call this once a human agent reviews/overrides an automated decision."""
        record = self._build_record(context)
        record["human_feedback"] = {
            "agent_decision_correct": agent_decision_correct,
            "notes": human_notes,
            "recorded_at": datetime.utcnow().isoformat(),
        }
        written = self._persist(record)
        return AgentResult(
            agent_name=self.name,
            success=written,
            data=record["human_feedback"],
            confidence=1.0 if written else 0.0,
            reasoning="Recorded human feedback on an automated decision for retraining.",
        )

    def _build_record(self, context: ComplaintContext) -> Dict[str, Any]:
        return {
            "complaint_id": context.complaint_id,
            "customer_id": context.customer_id,
            "category": context.category,
            "resolution": context.resolution,
            "fraud_score": context.fraud_score,
            "fraud_flags": context.fraud_flags,
            "escalated": context.escalated,
            "escalation_reason": context.escalation_reason,
            "final_workflow_state": context.workflow_state,
            "agent_trace_summary": [
                {"agent": e["agent_name"], "confidence": e["confidence"], "success": e["success"]}
                for e in context.agent_trace
            ],
            "logged_at": datetime.utcnow().isoformat(),
        }

    def _persist(self, record: Dict[str, Any]) -> bool:
        try:
            os.makedirs(os.path.dirname(self.feedback_store_path), exist_ok=True)
            with open(self.feedback_store_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
            return True
        except OSError:
            return False
