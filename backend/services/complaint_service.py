"""
Complaint service.

Business logic for creating, reading, updating, and managing complaints
and their evidence/audit trail. Routers (api/complaints.py) should call
into this layer instead of touching the ORM directly, so the same rules
apply whether the caller is the REST API, a background job, or an AI agent.
"""
import os
import shutil
import uuid
from datetime import datetime
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from database.models import (
    AuditLog, Complaint, ComplaintEvidence, ComplaintStatus, User, UserRole,
)
from services import notification_service, workflow_service

EVIDENCE_DIR = os.getenv("EVIDENCE_STORAGE_DIR", "storage/complaint_images")
os.makedirs(EVIDENCE_DIR, exist_ok=True)


class NotAuthorizedError(Exception):
    pass


class NotFoundError(Exception):
    pass


def _log(db: Session, complaint_id: str, actor_id: Optional[str], action: str, details: str = ""):
    db.add(AuditLog(complaint_id=complaint_id, actor_id=actor_id, action=action, details=details))


def create_complaint(
    db: Session, customer_id: str, title: str, description: str, category: Optional[str] = None
) -> Complaint:
    complaint = Complaint(
        customer_id=customer_id,
        title=title,
        description=description,
        category=category,
    )
    db.add(complaint)
    db.flush()
    _log(db, complaint.id, customer_id, "complaint_created")
    db.commit()
    db.refresh(complaint)

    notification_service.notify_user(
        db, customer_id, f"Your complaint '{title}' was received and is now open.",
        related_complaint_id=complaint.id,
    )
    return complaint


def get_complaint(db: Session, complaint_id: str, requesting_user: User) -> Complaint:
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise NotFoundError("Complaint not found")
    if requesting_user.role == UserRole.CUSTOMER and complaint.customer_id != requesting_user.id:
        raise NotAuthorizedError("Not authorized to view this complaint")
    return complaint


def list_complaints(
    db: Session,
    requesting_user: User,
    status_filter: Optional[ComplaintStatus] = None,
    category: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> Tuple[int, list]:
    query = db.query(Complaint)
    if requesting_user.role == UserRole.CUSTOMER:
        query = query.filter(Complaint.customer_id == requesting_user.id)
    if status_filter:
        query = query.filter(Complaint.status == status_filter)
    if category:
        query = query.filter(Complaint.category == category)

    total = query.count()
    items = (
        query.order_by(Complaint.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return total, items


def update_complaint(
    db: Session,
    complaint_id: str,
    actor: User,
    status: Optional[ComplaintStatus] = None,
    priority: Optional[str] = None,
    assigned_agent_id: Optional[str] = None,
    resolution_notes: Optional[str] = None,
) -> Complaint:
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise NotFoundError("Complaint not found")

    if status and status != complaint.status:
        # Delegate to the workflow service so the state machine and
        # notifications stay consistent no matter who calls this.
        workflow_service.transition_status(db, complaint, status, actor_id=actor.id, notes=resolution_notes)

    changed = {}
    if priority:
        complaint.priority = priority
        changed["priority"] = priority
    if assigned_agent_id:
        complaint.assigned_agent_id = assigned_agent_id
        changed["assigned_agent_id"] = assigned_agent_id
    if resolution_notes and status != ComplaintStatus.RESOLVED:
        complaint.resolution_notes = resolution_notes
        changed["resolution_notes"] = resolution_notes

    if changed:
        complaint.updated_at = datetime.utcnow()
        _log(db, complaint.id, actor.id, "complaint_updated", str(changed))
        db.commit()
        db.refresh(complaint)

    return complaint


def assign_complaint(db: Session, complaint_id: str, agent_id: str, actor: User) -> Complaint:
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise NotFoundError("Complaint not found")

    agent = db.query(User).filter(User.id == agent_id, User.role == UserRole.AGENT).first()
    if not agent:
        raise NotFoundError("Agent not found")

    complaint.assigned_agent_id = agent.id
    _log(db, complaint.id, actor.id, "complaint_assigned", f"agent={agent.id}")
    db.commit()
    db.refresh(complaint)

    notification_service.notify_user(
        db, agent.id, f"You have been assigned complaint '{complaint.title}'.",
        related_complaint_id=complaint.id,
    )
    return complaint


def delete_complaint(db: Session, complaint_id: str) -> bool:
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise NotFoundError("Complaint not found")
    db.delete(complaint)
    db.commit()
    return True


def add_evidence(db: Session, complaint_id: str, upload_file, actor: User) -> ComplaintEvidence:
    """
    Store an uploaded evidence file (image/document) against a complaint.
    `upload_file` is expected to be a FastAPI UploadFile.
    """
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise NotFoundError("Complaint not found")
    if actor.role == UserRole.CUSTOMER and complaint.customer_id != actor.id:
        raise NotAuthorizedError("Not authorized to modify this complaint")

    ext = os.path.splitext(upload_file.filename or "")[1].lower()
    file_type = "image" if ext in (".jpg", ".jpeg", ".png", ".webp") else "document"
    stored_name = f"{uuid.uuid4()}{ext}"
    dest_path = os.path.join(EVIDENCE_DIR, stored_name)

    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)

    evidence = ComplaintEvidence(complaint_id=complaint.id, file_path=dest_path, file_type=file_type)
    db.add(evidence)
    _log(db, complaint.id, actor.id, "evidence_uploaded", stored_name)
    db.commit()
    db.refresh(evidence)
    return evidence


def get_history(db: Session, complaint_id: str, requesting_user: User) -> list:
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise NotFoundError("Complaint not found")
    if requesting_user.role == UserRole.CUSTOMER and complaint.customer_id != requesting_user.id:
        raise NotAuthorizedError("Not authorized to view this complaint")

    return (
        db.query(AuditLog)
        .filter(AuditLog.complaint_id == complaint_id)
        .order_by(AuditLog.created_at.desc())
        .all()
    )
