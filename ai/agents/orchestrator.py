"""
orchestrator.py
Coordinates the full Resolvix-AI multi-agent pipeline.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .base_agent import AgentResult, ComplaintContext
from .customer_agent import CustomerAgent
from .evidence_agent import EvidenceAgent
from .fraud_agent import FraudAgent
from .policy_agent import PolicyAgent
from .resolution_agent import ResolutionAgent
from .workflow_agent import WorkflowAgent
from .escalation_agent import EscalationAgent
from .learning_agent import LearningAgent

logger = logging.getLogger("resolvix.orchestrator")


class Orchestrator:

    def __init__(
        self,
        llm_client: Any = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        config = config or {}

        self.customer_agent = CustomerAgent(
            llm_client,
            config.get("customer_agent"),
        )

        self.evidence_agent = EvidenceAgent(
            llm_client,
            config.get("evidence_agent"),
        )

        self.policy_agent = PolicyAgent(
            llm_client,
            config.get("policy_agent"),
        )

        self.fraud_agent = FraudAgent(
            llm_client,
            config.get("fraud_agent"),
        )

        self.resolution_agent = ResolutionAgent(
            llm_client,
            config.get("resolution_agent"),
        )

        self.escalation_agent = EscalationAgent(
            llm_client,
            config.get("escalation_agent"),
        )

        self.workflow_agent = WorkflowAgent(
            llm_client,
            config.get("workflow_agent"),
        )

        self.learning_agent = LearningAgent(
            llm_client,
            config.get("learning_agent"),
        )

    def handle_complaint(
        self,
        complaint_id: str,
        customer_id: str,
        raw_text: str,
        channel: str = "web",
        attachments: Optional[List[str]] = None,
    ) -> ComplaintContext:

        context = ComplaintContext(
            complaint_id=complaint_id,
            customer_id=customer_id,
            raw_text=raw_text,
            channel=channel,
            attachments=attachments or [],
        )

        logger.info(
            "Starting pipeline for complaint %s",
            complaint_id,
        )

        self._advance_workflow(context)

        self.customer_agent.run(context)

        if context.attachments:
            self._advance_workflow(context)
            self.evidence_agent.run(context)

        self._advance_workflow(context)

        self.policy_agent.run(context)

        self._advance_workflow(context)

        self.fraud_agent.run(context)

        self.resolution_agent.run(context)

        self.escalation_agent.run(context)

        self._advance_workflow(context)

        if not context.escalated:
            self._advance_workflow(context)

        self.learning_agent.run(context)

        logger.info(
            "Completed pipeline for complaint %s",
            complaint_id,
        )

        return context

    def _advance_workflow(
        self,
        context: ComplaintContext,
    ) -> AgentResult:

        result = self.workflow_agent.run(context)

        if not result.success:
            logger.warning(
                "Workflow transition failed for %s: %s",
                context.complaint_id,
                result.error,
            )

        return result

    def explain(
        self,
        context: ComplaintContext,
    ) -> Dict[str, Any]:

        return {
            "complaint_id": context.complaint_id,
            "final_state": context.workflow_state,
            "category": context.category,
            "resolution": context.resolution,
            "fraud_score": context.fraud_score,
            "fraud_flags": context.fraud_flags,
            "escalated": context.escalated,
            "escalation_reason": context.escalation_reason,
            "steps": context.agent_trace,
        }


if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO)

    orchestrator = Orchestrator()

    context = orchestrator.handle_complaint(
        complaint_id="CMP-1001",
        customer_id="CUST-42",
        raw_text="My phone arrived with a cracked screen and I need a refund.",
        attachments=["storage/complaint_image/photo2.webp"],
    )

    import json

    print(json.dumps(orchestrator.explain(context), indent=2))