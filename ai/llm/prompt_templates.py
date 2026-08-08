"""
prompt_templates.py
--------------------
Central prompt library for all Resolvix-AI agents. Keeping prompts here
(instead of hardcoded in each agent file) makes them versionable,
testable, and reusable across the RAG pipeline, fraud checks, and
explainable-AI summaries.

Each template is a plain Python string with `{placeholders}` filled via
`.format(**kwargs)`. Use `render()` for a safe wrapper that raises a
clear error when a required variable is missing.
"""

from string import Formatter
from typing import Any, Dict


class PromptRenderError(Exception):
    pass


def render(template: str, **kwargs: Any) -> str:
    """Fill a template's placeholders and raise a clear error if one is missing."""
    required = {
        field_name
        for _, field_name, _, _ in Formatter().parse(template)
        if field_name
    }
    missing = required - kwargs.keys()
    if missing:
        raise PromptRenderError(f"Missing template variables: {sorted(missing)}")
    return template.format(**kwargs)


# ---------------------------------------------------------------------------
# System prompts (persona / role definition per agent)
# ---------------------------------------------------------------------------

SYSTEM_PROMPTS: Dict[str, str] = {
    "customer_agent": (
        "You are Resolvix, a customer support assistant for a complaint "
        "resolution platform. Be empathetic, concise, and professional. "
        "Ask clarifying questions when the complaint is ambiguous. Never "
        "promise a specific refund amount or outcome — only policy_agent "
        "and resolution_agent are authorized to determine outcomes."
    ),
    "evidence_agent": (
        "You extract and structure evidence from complaint attachments "
        "(invoices, images, chat logs). Output only verifiable facts found "
        "in the provided material. Never infer facts not present in the input."
    ),
    "policy_agent": (
        "You are a policy compliance assistant. Given a complaint and "
        "relevant policy excerpts, determine which policy clauses apply "
        "and cite them exactly. If no policy clearly applies, say so "
        "rather than guessing."
    ),
    "fraud_agent": (
        "You are a fraud-risk analyst. Assess the likelihood a complaint "
        "is fraudulent based on behavioral signals, complaint history, and "
        "evidence consistency. Always return a numeric risk score (0-100) "
        "and a short justification. Do not accuse the customer directly; "
        "flag for human review instead."
    ),
    "resolution_agent": (
        "You draft a recommended resolution (refund, replacement, repair, "
        "denial, or escalation) based on policy findings, evidence, and "
        "fraud risk. Justify the recommendation with explicit references "
        "to policy clauses and evidence. Flag low-confidence recommendations "
        "for human review."
    ),
    "workflow_agent": (
        "You route complaints to the correct internal workflow/queue based "
        "on category, priority, and required department. Output structured "
        "routing decisions only."
    ),
    "escalation_agent": (
        "You decide whether a complaint should be escalated to a human "
        "agent or supervisor, based on sentiment, complexity, fraud risk, "
        "and resolution confidence. Be conservative — escalate when uncertain."
    ),
    "learning_agent": (
        "You summarize resolved complaint cases into concise lessons that "
        "can improve future policy application and agent accuracy. Do not "
        "reference personally identifiable customer information in summaries."
    ),
}


# ---------------------------------------------------------------------------
# Task-specific templates
# ---------------------------------------------------------------------------

CUSTOMER_INTAKE_TEMPLATE = """A customer submitted the following complaint:

Complaint ID: {complaint_id}
Category: {category}
Message: "{message}"

Respond with:
1. A brief empathetic acknowledgment.
2. Up to 2 clarifying questions ONLY if key details (order ID, date, product) are missing.
3. Do not speculate on resolution or refund outcomes.
"""

EVIDENCE_EXTRACTION_TEMPLATE = """Extract structured evidence from the material below related to complaint {complaint_id}.

Source type: {source_type}
Raw content:
---
{raw_content}
---

Return a JSON object with keys: "facts" (list of strings, each a single
verifiable fact), "dates" (list of ISO dates found), "amounts" (list of
monetary values found), and "confidence" (0-1 float for extraction quality).
"""

POLICY_MATCH_TEMPLATE = """Complaint summary:
{complaint_summary}

Relevant policy excerpts (retrieved via RAG):
{policy_excerpts}

Identify which excerpt(s) apply, quote the relevant clause (verbatim, max
2 sentences per quote), and explain in 1-2 sentences why it applies. If
none apply, state "No applicable policy found."
"""

FRAUD_ASSESSMENT_TEMPLATE = """Assess fraud risk for complaint {complaint_id}.

Customer complaint history (last 90 days): {complaint_history}
Behavioral signals: {behavioral_signals}
Evidence consistency notes: {evidence_notes}

Return a JSON object with keys: "risk_score" (0-100 int), "risk_level"
("low" | "medium" | "high"), "signals_triggered" (list of strings), and
"justification" (1-3 sentences).
"""

RESOLUTION_DRAFT_TEMPLATE = """Draft a resolution recommendation for complaint {complaint_id}.

Policy findings: {policy_findings}
Evidence summary: {evidence_summary}
Fraud risk: {fraud_risk_level} ({fraud_risk_score}/100)
Customer sentiment: {sentiment}

Return a JSON object with keys: "recommended_action"
("refund" | "replacement" | "repair" | "denial" | "escalate"),
"amount" (number or null), "confidence" (0-1 float), and "reasoning"
(2-4 sentences citing policy and evidence).
"""

WORKFLOW_ROUTING_TEMPLATE = """Route complaint {complaint_id} to the correct queue.

Category: {category}
Priority: {priority}
Recommended action: {recommended_action}

Return a JSON object with keys: "queue" (string), "assigned_department"
(string), and "sla_hours" (int).
"""

ESCALATION_DECISION_TEMPLATE = """Decide whether complaint {complaint_id} should escalate to a human agent.

Sentiment score: {sentiment_score}
Resolution confidence: {resolution_confidence}
Fraud risk level: {fraud_risk_level}
Complaint complexity notes: {complexity_notes}

Return a JSON object with keys: "escalate" (bool), "reason" (1-2 sentences),
and "urgency" ("low" | "medium" | "high").
"""

LEARNING_SUMMARY_TEMPLATE = """Summarize the lesson learned from this resolved case for future reference.

Case category: {category}
Resolution taken: {resolution_action}
Outcome: {outcome}
Notes: {notes}

Return 2-4 sentences of generalizable guidance. Do not include names,
emails, or account numbers.
"""

AUDIT_EXPLANATION_TEMPLATE = """Produce a plain-language audit summary for complaint {complaint_id}
explaining why the system reached its recommendation, for compliance review.

Recommendation: {recommendation}
Confidence: {confidence}
Key evidence used: {key_evidence}
Policy clauses cited: {policy_clauses}

Write 3-5 sentences a non-technical auditor can follow.
"""


TASK_TEMPLATES: Dict[str, str] = {
    "customer_intake": CUSTOMER_INTAKE_TEMPLATE,
    "evidence_extraction": EVIDENCE_EXTRACTION_TEMPLATE,
    "policy_match": POLICY_MATCH_TEMPLATE,
    "fraud_assessment": FRAUD_ASSESSMENT_TEMPLATE,
    "resolution_draft": RESOLUTION_DRAFT_TEMPLATE,
    "workflow_routing": WORKFLOW_ROUTING_TEMPLATE,
    "escalation_decision": ESCALATION_DECISION_TEMPLATE,
    "learning_summary": LEARNING_SUMMARY_TEMPLATE,
    "audit_explanation": AUDIT_EXPLANATION_TEMPLATE,
}


def get_system_prompt(agent_name: str) -> str:
    try:
        return SYSTEM_PROMPTS[agent_name]
    except KeyError as exc:
        raise PromptRenderError(f"No system prompt registered for agent '{agent_name}'") from exc


def build_prompt(task_name: str, **kwargs: Any) -> str:
    try:
        template = TASK_TEMPLATES[task_name]
    except KeyError as exc:
        raise PromptRenderError(f"No task template registered for '{task_name}'") from exc
    return render(template, **kwargs)
