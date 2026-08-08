"""
Workflow service.

Owns the complaint state machine: which status transitions are legal,
SLA deadline calculation, auto-escalation rules, and agent
auto-assignment. This is where the "business rules" of Resolvix-AI
live, separate from HTTP concerns (routers) and persistence (models).
"""
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from database.models import (
    AuditLog, Complaint, ComplaintPriority, ComplaintStatus, User, UserRole,
)
from services import notification_service

# Legal status transitions. Anything not listed here is rejected.
ALLOWED_TRANSITIONS = {
    ComplaintStatus.OPEN: {ComplaintStatus.IN_REVIEW, ComplaintStatus.REJECTED},
    ComplaintStatus.IN_REVIEW: {ComplaintStatus.ESCALATED, ComplaintStatus.RESOLVED, ComplaintStatus.REJECTED},
    ComplaintStatus.ESCALATED: {ComplaintStatus.IN_REVIEW, ComplaintStatus.RESOLVED, ComplaintStatus.REJECTED},
    ComplaintStatus.RESOLVED: set(),   # terminal
    ComplaintStatus.REJECTED: set(),   # terminal
}

# SLA target, in hours, before a complaint should be auto-flagged as overdue.
SLA_HOURS_BY_PRIORITY = {
    ComplaintPriority.CRITICAL: 4,
    ComplaintPriority.HIGH: 24,
    ComplaintPriority.MEDIUM: 72,
    ComplaintPriority.LOW: 168,
}

# Fraud score at or above this triggers an automatic staff alert.
FRAUD_ALERT_THRESHOLD = 0.7


class InvalidTransitionError(Exception):
    pass


def is_transition_allowed(current: ComplaintStatus, target: ComplaintStatus) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())


def sla_deadline(complaint: Complaint) -> datetime:
    hours = SLA_HOURS_BY_PRIORITY.get(complaint.priority, 72)
    return complaint.created_at + timedelta(hours=hours)


def is_overdue(complaint: Complaint) -> bool:
    if complaint.status in (ComplaintStatus.RESOLVED, ComplaintStatus.REJECTED):
        return False
    return datetime.utcnow() > sla_deadline(complaint)


def transition_status(
    db: Session,
    complaint: Complaint,
    new_status: ComplaintStatus,
    actor_id: Optional[str] = None,
    notes: Optional[str] = None,
) -> Complaint:
    """
    Move a complaint to a new status, enforcing the state machine,
    stamping resolved_at, logging the change, and notifying the customer.
    """
    if not is_transition_allowed(complaint.status, new_status):
        raise InvalidTransitionError(
            f"Cannot move complaint from {complaint.status.value} to {new_status.value}"
        )

    old_status = complaint.status
    complaint.status = new_status
    complaint.updated_at = datetime.utcnow()

    if new_status == ComplaintStatus.RESOLVED:
        complaint.resolved_at = datetime.utcnow()
        if notes:
            complaint.resolution_notes = notes

    db.add(AuditLog(
        complaint_id=complaint.id,
        actor_id=actor_id,
        action="status_transition",
        details=f"{old_status.value} -> {new_status.value}",
    ))
    db.commit()
    db.refresh(complaint)

    notification_service.notify_status_change(db, complaint, old_status.value, new_status.value)
    if new_status == ComplaintStatus.ESCALATED:
        notification_service.notify_escalation(db, complaint)

    return complaint


def apply_ai_signals(
    db: Session,
    complaint: Complaint,
    fraud_score: Optional[float] = None,
    confidence_score: Optional[float] = None,
    sentiment_score: Optional[float] = None,
    ai_summary: Optional[str] = None,
) -> Complaint:
    """
    Apply AI-agent output (fraud/confidence/sentiment) to a complaint and
    run the automatic escalation rules that depend on those scores.
    Intended to be called by ai/agents/orchestrator.py after inference.
    """
    if fraud_score is not None:
        complaint.fraud_score = fraud_score
    if confidence_score is not None:
        complaint.confidence_score = confidence_score
    if sentiment_score is not None:
        complaint.sentiment_score = sentiment_score
    if ai_summary is not None:
        complaint.ai_summary = ai_summary

    db.commit()
    db.refresh(complaint)

    if fraud_score is not None and fraud_score >= FRAUD_ALERT_THRESHOLD:
        notification_service.notify_fraud_alert(db, complaint)
        if complaint.status == ComplaintStatus.OPEN:
            complaint.priority = ComplaintPriority.HIGH
            db.commit()

    # Very negative sentiment auto-escalates a still-open complaint.
    if sentiment_score is not None and sentiment_score <= -0.6 and complaint.status == ComplaintStatus.OPEN:
        try:
            transition_status(db, complaint, ComplaintStatus.ESCALATED, notes="Auto-escalated: negative sentiment")
        except InvalidTransitionError:
            pass

    return complaint


def auto_assign_agent(db: Session, complaint: Complaint) -> Optional[User]:
    """
    Assign the complaint to whichever active agent currently has the
    fewest open (non-terminal) complaints — a simple load-balancing rule.
    """
    agents = db.query(User).filter(User.role == UserRole.AGENT, User.is_active.is_(True)).all()
    if not agents:
        return None

    best_agent = None
    best_load = None
    for agent in agents:
        load = (
            db.query(func.count(Complaint.id))
            .filter(
                Complaint.assigned_agent_id == agent.id,
                Complaint.status.notin_([ComplaintStatus.RESOLVED, ComplaintStatus.REJECTED]),
            )
            .scalar() or 0
        )
        if best_load is None or load < best_load:
            best_agent, best_load = agent, load

    complaint.assigned_agent_id = best_agent.id
    db.add(AuditLog(
        complaint_id=complaint.id,
        actor_id=None,
        action="auto_assigned",
        details=f"agent={best_agent.id}",
    ))
    db.commit()
    db.refresh(complaint)

    notification_service.notify_user(
        db, best_agent.id, f"You have been assigned complaint '{complaint.title}'.",
        related_complaint_id=complaint.id,
    )
    return best_agent


def get_overdue_complaints(db: Session):
    """Returns all non-terminal complaints that have breached their SLA."""
    open_complaints = db.query(Complaint).filter(
        Complaint.status.notin_([ComplaintStatus.RESOLVED, ComplaintStatus.REJECTED])
    ).all()
    return [c for c in open_complaints if is_overdue(c)]
