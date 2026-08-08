"""
Report service.

Builds the actual report content (CSV files today; swap in a PDF/xlsx
writer here without touching the API layer) and the aggregate stats
used by the admin dashboard. api/reports.py and api/dashboard.py should
delegate to this module rather than querying models directly.
"""
import csv
import os
from datetime import datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from database.connection import SessionLocal
from database.models import Complaint, ComplaintStatus, Report, User, UserRole

REPORTS_DIR = os.getenv("REPORTS_STORAGE_DIR", "storage/generated_reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

REPORT_COLUMNS = [
    "id", "title", "status", "priority", "fraud_score",
    "confidence_score", "created_at", "resolved_at",
]


def _complaint_row(c: Complaint) -> list:
    return [
        c.id, c.title, c.status.value, c.priority.value,
        c.fraud_score, c.confidence_score, c.created_at, c.resolved_at,
    ]


def _filtered_complaints(db: Session, report_type: str, date_from, date_to):
    query = db.query(Complaint)
    if date_from:
        query = query.filter(Complaint.created_at >= date_from)
    if date_to:
        query = query.filter(Complaint.created_at <= date_to)
    if report_type == "fraud":
        query = query.filter(Complaint.fraud_score >= 0.5)
    return query.all()


def create_report_request(
    db: Session, requested_by: str, report_type: str,
    date_from: Optional[datetime] = None, date_to: Optional[datetime] = None,
) -> Report:
    report = Report(
        requested_by=requested_by,
        report_type=report_type,
        date_from=date_from,
        date_to=date_to,
        status="pending",
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def generate_report_file(report_id: str, report_type: str, date_from, date_to) -> None:
    """
    Runs as a background task. Opens its own DB session since it executes
    outside the request/response cycle where the router's session lives.
    """
    db = SessionLocal()
    try:
        report = db.query(Report).filter(Report.id == report_id).first()
        if not report:
            return

        if report_type == "agent_performance":
            file_path = _write_agent_performance_csv(db, report_id)
        else:
            complaints = _filtered_complaints(db, report_type, date_from, date_to)
            file_path = os.path.join(REPORTS_DIR, f"{report_id}.csv")
            with open(file_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(REPORT_COLUMNS)
                for c in complaints:
                    writer.writerow(_complaint_row(c))

        report.file_path = file_path
        report.status = "ready"
        db.commit()
    except Exception:
        report = db.query(Report).filter(Report.id == report_id).first()
        if report:
            report.status = "failed"
            db.commit()
    finally:
        db.close()


def _write_agent_performance_csv(db: Session, report_id: str) -> str:
    file_path = os.path.join(REPORTS_DIR, f"{report_id}.csv")
    agents = db.query(User).filter(User.role == UserRole.AGENT).all()

    with open(file_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["agent_id", "agent_name", "assigned", "resolved", "resolution_rate"])
        for agent in agents:
            assigned = db.query(func.count(Complaint.id)).filter(
                Complaint.assigned_agent_id == agent.id
            ).scalar() or 0
            resolved = db.query(func.count(Complaint.id)).filter(
                Complaint.assigned_agent_id == agent.id,
                Complaint.status == ComplaintStatus.RESOLVED,
            ).scalar() or 0
            rate = round(resolved / assigned, 2) if assigned else 0.0
            writer.writerow([agent.id, agent.name, assigned, resolved, rate])

    return file_path


def get_report(db: Session, report_id: str) -> Optional[Report]:
    return db.query(Report).filter(Report.id == report_id).first()


def list_reports(db: Session, requesting_user: User) -> list:
    query = db.query(Report)
    if requesting_user.role != UserRole.ADMIN:
        query = query.filter(Report.requested_by == requesting_user.id)
    return query.order_by(Report.created_at.desc()).all()


# ---------- Dashboard aggregate stats (shared with api/dashboard.py) ----------

def dashboard_summary(db: Session) -> dict:
    total = db.query(func.count(Complaint.id)).scalar() or 0
    open_count = db.query(func.count(Complaint.id)).filter(
        Complaint.status == ComplaintStatus.OPEN
    ).scalar() or 0
    resolved_count = db.query(func.count(Complaint.id)).filter(
        Complaint.status == ComplaintStatus.RESOLVED
    ).scalar() or 0
    escalated_count = db.query(func.count(Complaint.id)).filter(
        Complaint.status == ComplaintStatus.ESCALATED
    ).scalar() or 0
    high_fraud_count = db.query(func.count(Complaint.id)).filter(
        Complaint.fraud_score >= 0.7
    ).scalar() or 0

    avg_seconds = db.query(
        func.avg(func.extract("epoch", Complaint.resolved_at - Complaint.created_at))
    ).filter(Complaint.resolved_at.isnot(None)).scalar()
    avg_hours = round(avg_seconds / 3600, 2) if avg_seconds else None

    breakdown_rows = (
        db.query(Complaint.status, func.count(Complaint.id))
        .group_by(Complaint.status)
        .all()
    )

    return {
        "total_complaints": total,
        "open_complaints": open_count,
        "resolved_complaints": resolved_count,
        "escalated_complaints": escalated_count,
        "avg_resolution_hours": avg_hours,
        "status_breakdown": [{"status": s.value, "count": c} for s, c in breakdown_rows],
        "high_fraud_count": high_fraud_count,
    }


def daily_trends(db: Session, days: int = 14) -> list:
    from datetime import timedelta
    since = datetime.utcnow() - timedelta(days=days)
    rows = (
        db.query(func.date(Complaint.created_at), func.count(Complaint.id))
        .filter(Complaint.created_at >= since)
        .group_by(func.date(Complaint.created_at))
        .order_by(func.date(Complaint.created_at))
        .all()
    )
    return [{"date": str(d), "count": c} for d, c in rows]


def agent_performance(db: Session) -> list:
    agents = db.query(User).filter(User.role == UserRole.AGENT).all()
    performance = []
    for agent in agents:
        assigned = db.query(func.count(Complaint.id)).filter(
            Complaint.assigned_agent_id == agent.id
        ).scalar() or 0
        resolved = db.query(func.count(Complaint.id)).filter(
            Complaint.assigned_agent_id == agent.id,
            Complaint.status == ComplaintStatus.RESOLVED,
        ).scalar() or 0
        performance.append({
            "agent_id": agent.id,
            "agent_name": agent.name,
            "assigned": assigned,
            "resolved": resolved,
            "resolution_rate": round(resolved / assigned, 2) if assigned else 0.0,
        })
    return performance
