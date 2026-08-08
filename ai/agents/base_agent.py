"""
base_agent.py
Shared base class for all Resolvix-AI agents.

Every specialized agent (Customer, Evidence, Policy, Fraud, Resolution,
Workflow, Escalation, Learning) inherits from BaseAgent so that the
Orchestrator can treat them uniformly: call `.run(context)`, get back an
AgentResult, and merge it into the shared ComplaintContext.
"""

from __future__ import annotations

import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


logger = logging.getLogger("resolvix.agents")


@dataclass
class AgentResult:
    """Standard output every agent returns."""
    agent_name: str
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0          # 0.0 - 1.0
    reasoning: str = ""              # human-readable explanation (for explainable_ai)
    error: Optional[str] = None
    duration_ms: float = 0.0
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "success": self.success,
            "data": self.data,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "trace_id": self.trace_id,
            "timestamp": self.timestamp,
        }


@dataclass
class ComplaintContext:
    """
    The shared 'blackboard' object passed between agents.
    Each agent reads what it needs and writes its findings back here.
    """
    complaint_id: str
    customer_id: str
    raw_text: str
    channel: str = "web"                     # web, email, chat, phone
    attachments: list = field(default_factory=list)   # image/invoice paths or URLs
    intent: Optional[str] = None
    category: Optional[str] = None
    sentiment: Optional[str] = None
    priority: Optional[str] = None
    evidence_findings: Dict[str, Any] = field(default_factory=dict)
    policy_findings: Dict[str, Any] = field(default_factory=dict)
    fraud_score: Optional[float] = None
    fraud_flags: list = field(default_factory=list)
    resolution: Optional[Dict[str, Any]] = None
    workflow_state: str = "received"
    escalated: bool = False
    escalation_reason: Optional[str] = None
    agent_trace: list = field(default_factory=list)  # list[AgentResult.to_dict()]

    def log(self, result: AgentResult) -> None:
        self.agent_trace.append(result.to_dict())


class BaseAgent(ABC):
    """
    Abstract base class. Subclasses implement `process()`.
    `run()` wraps `process()` with timing, logging and error handling so
    individual agents stay focused on their own logic.
    """

    name: str = "base_agent"

    def __init__(self, llm_client: Any = None, config: Optional[Dict[str, Any]] = None):
        self.llm = llm_client
        self.config = config or {}

    @abstractmethod
    def process(self, context: ComplaintContext) -> AgentResult:
        """Implement agent-specific logic. Must return an AgentResult."""
        raise NotImplementedError

    def run(self, context: ComplaintContext) -> AgentResult:
        start = time.perf_counter()
        try:
            result = self.process(context)
        except Exception as exc:  # noqa: BLE001
            logger.exception("%s failed on complaint %s", self.name, context.complaint_id)
            result = AgentResult(
                agent_name=self.name,
                success=False,
                error=str(exc),
                reasoning=f"{self.name} raised an unhandled exception.",
            )
        result.duration_ms = round((time.perf_counter() - start) * 1000, 2)
        context.log(result)
        return result
