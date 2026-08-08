"""
response_parser.py
-------------------
Parses raw text returned by model_loader clients into structured,
validated Python objects that downstream services (complaint_service,
report_service, explainable_ai/*) can consume safely.

LLMs occasionally wrap JSON in markdown fences, add stray commentary, or
produce minor formatting issues — this module normalizes and validates
against expected schemas per task, and raises typed errors instead of
letting bad data flow silently into the pipeline.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("resolvix.ai.response_parser")

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


class ResponseParseError(Exception):
    """Raised when a model response can't be parsed or fails validation."""

    def __init__(self, message: str, raw_response: str = ""):
        super().__init__(message)
        self.raw_response = raw_response


# ---------------------------------------------------------------------------
# Low-level cleanup / JSON extraction
# ---------------------------------------------------------------------------

def strip_code_fences(text: str) -> str:
    return _CODE_FENCE_RE.sub("", text).strip()


def extract_json_block(text: str) -> str:
    """
    Best-effort extraction of the first JSON object in a string, in case
    the model added preamble/postamble text around the JSON.
    """
    cleaned = strip_code_fences(text)
    match = _JSON_OBJECT_RE.search(cleaned)
    if not match:
        raise ResponseParseError("No JSON object found in model response", raw_response=text)
    return match.group(0)


def parse_json(text: str) -> Dict[str, Any]:
    """Parse a model response into a dict, tolerating fences/preamble."""
    candidate = strip_code_fences(text)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    # Fallback: try to isolate just the {...} block
    block = extract_json_block(text)
    try:
        return json.loads(block)
    except json.JSONDecodeError as exc:
        raise ResponseParseError(f"Could not parse JSON from response: {exc}", raw_response=text) from exc


def _require_keys(data: Dict[str, Any], keys: List[str], raw: str) -> None:
    missing = [k for k in keys if k not in data]
    if missing:
        raise ResponseParseError(f"Response missing required keys: {missing}", raw_response=raw)


# ---------------------------------------------------------------------------
# Structured result types (one per task template in prompt_templates.py)
# ---------------------------------------------------------------------------

@dataclass
class EvidenceExtractionResult:
    facts: List[str]
    dates: List[str]
    amounts: List[float]
    confidence: float


@dataclass
class FraudAssessmentResult:
    risk_score: int
    risk_level: str
    signals_triggered: List[str]
    justification: str


@dataclass
class ResolutionDraftResult:
    recommended_action: str
    amount: Optional[float]
    confidence: float
    reasoning: str


@dataclass
class WorkflowRoutingResult:
    queue: str
    assigned_department: str
    sla_hours: int


@dataclass
class EscalationDecisionResult:
    escalate: bool
    reason: str
    urgency: str


VALID_ACTIONS = {"refund", "replacement", "repair", "denial", "escalate"}
VALID_RISK_LEVELS = {"low", "medium", "high"}
VALID_URGENCY = {"low", "medium", "high"}


# ---------------------------------------------------------------------------
# Per-task parsers
# ---------------------------------------------------------------------------

def parse_evidence_extraction(raw: str) -> EvidenceExtractionResult:
    data = parse_json(raw)
    _require_keys(data, ["facts", "dates", "amounts", "confidence"], raw)
    return EvidenceExtractionResult(
        facts=list(data["facts"]),
        dates=list(data["dates"]),
        amounts=[float(a) for a in data["amounts"]],
        confidence=max(0.0, min(1.0, float(data["confidence"]))),
    )


def parse_fraud_assessment(raw: str) -> FraudAssessmentResult:
    data = parse_json(raw)
    _require_keys(data, ["risk_score", "risk_level", "signals_triggered", "justification"], raw)

    risk_score = int(data["risk_score"])
    if not 0 <= risk_score <= 100:
        raise ResponseParseError(f"risk_score out of bounds: {risk_score}", raw_response=raw)

    risk_level = str(data["risk_level"]).lower()
    if risk_level not in VALID_RISK_LEVELS:
        raise ResponseParseError(f"Invalid risk_level: {risk_level}", raw_response=raw)

    return FraudAssessmentResult(
        risk_score=risk_score,
        risk_level=risk_level,
        signals_triggered=list(data["signals_triggered"]),
        justification=str(data["justification"]).strip(),
    )


def parse_resolution_draft(raw: str) -> ResolutionDraftResult:
    data = parse_json(raw)
    _require_keys(data, ["recommended_action", "amount", "confidence", "reasoning"], raw)

    action = str(data["recommended_action"]).lower()
    if action not in VALID_ACTIONS:
        raise ResponseParseError(f"Invalid recommended_action: {action}", raw_response=raw)

    amount = data["amount"]
    amount = float(amount) if amount is not None else None

    return ResolutionDraftResult(
        recommended_action=action,
        amount=amount,
        confidence=max(0.0, min(1.0, float(data["confidence"]))),
        reasoning=str(data["reasoning"]).strip(),
    )


def parse_workflow_routing(raw: str) -> WorkflowRoutingResult:
    data = parse_json(raw)
    _require_keys(data, ["queue", "assigned_department", "sla_hours"], raw)
    return WorkflowRoutingResult(
        queue=str(data["queue"]).strip(),
        assigned_department=str(data["assigned_department"]).strip(),
        sla_hours=int(data["sla_hours"]),
    )


def parse_escalation_decision(raw: str) -> EscalationDecisionResult:
    data = parse_json(raw)
    _require_keys(data, ["escalate", "reason", "urgency"], raw)

    urgency = str(data["urgency"]).lower()
    if urgency not in VALID_URGENCY:
        raise ResponseParseError(f"Invalid urgency: {urgency}", raw_response=raw)

    return EscalationDecisionResult(
        escalate=bool(data["escalate"]),
        reason=str(data["reason"]).strip(),
        urgency=urgency,
    )


# ---------------------------------------------------------------------------
# Dispatch table so orchestrator.py can parse generically by task name
# ---------------------------------------------------------------------------

PARSERS = {
    "evidence_extraction": parse_evidence_extraction,
    "fraud_assessment": parse_fraud_assessment,
    "resolution_draft": parse_resolution_draft,
    "workflow_routing": parse_workflow_routing,
    "escalation_decision": parse_escalation_decision,
}


def parse_response(task_name: str, raw: str) -> Any:
    """
    Generic entry point: given the task name (matching prompt_templates.TASK_TEMPLATES)
    and the raw LLM text, return the corresponding validated dataclass.
    Falls back to returning the raw parsed dict for tasks without a strict schema
    (e.g. customer_intake, learning_summary, audit_explanation are free-text tasks).
    """
    parser = PARSERS.get(task_name)
    if parser is None:
        logger.debug("No strict parser for task '%s'; returning stripped text.", task_name)
        return strip_code_fences(raw)

    try:
        return parser(raw)
    except ResponseParseError:
        raise
    except Exception as exc:  # noqa: BLE001 - normalize any parser failure
        raise ResponseParseError(f"Unexpected parsing failure: {exc}", raw_response=raw) from exc
