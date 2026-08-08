"""
Report generation endpoints. Reports are generated as CSV files and
tracked in the `reports` table; swap `_write_csv_report` for a call
into services/report_service.py for richer PDF/analytics output.
"""
import csv
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from core.security import require_roles
from database.connection import get_db
from database.models import Complaint, Report, User, UserRole
from database.schemas import ReportOut, ReportRequest

router = APIRouter(prefix="/reports", tags=["Reports"])

REPORTS_DIR = os.getenv("REPORTS_STORAGE_DIR", "storage/generated_reports")
os.makedirs(REPORTS_DIR, exist_ok=True)


def _generate_report_file(report_id: str, report_type: str,
                           date_from: Optional[datetime], date_to: Optional[datetime],
                           db_url_session_factory):
    """Runs in the background: queries complaints and writes a CSV file."""
    from database.connection import SessionLocal
    db = SessionLocal()
    try:
        report = db.query(Report).filter(Report.id == report_id).first()
        if not report:
            return

        query = db.query(Complaint)
        if date_from:
            query = query.filter(Complaint.created_at >= date_from)
        if date_to:
            query = query.filter(Complaint.created_at <= date_to)
        if report_type == "fraud":
            query = query.filter(Complaint.fraud_score >= 0.5)

        complaints = query.all()
        file_path = os.path.join(REPORTS_DIR, f"{report_id}.csv")

        with open(file_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "id", "title", "status", "priority", "fraud_score",
                "confidence_score", "created_at", "resolved_at",
            ])
            for c in complaints:
                writer.writerow([
                    c.id, c.title, c.status.value, c.priority.value,
                    c.fraud_score, c.confidence_score, c.created_at, c.resolved_at,
                ])

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


@router.post("/generate", response_model=ReportOut)
def generate_report(
    payload: ReportRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.AGENT, UserRole.ADMIN)),
):
    report = Report(
        requested_by=current_user.id,
        report_type=payload.report_type,
        date_from=payload.date_from,
        date_to=payload.date_to,
        status="pending",
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    background_tasks.add_task(
        _generate_report_file, report.id, payload.report_type,
        payload.date_from, payload.date_to, None,
    )
    return report


@router.get("/", response_model=list[ReportOut])
def list_reports(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.AGENT, UserRole.ADMIN)),
):
    query = db.query(Report)
    if current_user.role != UserRole.ADMIN:
        query = query.filter(Report.requested_by == current_user.id)
    return query.order_by(Report.created_at.desc()).all()


@router.get("/{report_id}", response_model=ReportOut)
def get_report(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.AGENT, UserRole.ADMIN)),
):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.get("/{report_id}/download")
def download_report(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.AGENT, UserRole.ADMIN)),
):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.status != "ready" or not report.file_path:
        raise HTTPException(status_code=409, detail=f"Report is not ready (status={report.status})")

    return FileResponse(
        path=report.file_path,
        filename=f"resolvix_report_{report.report_type}_{report_id}.csv",
        media_type="text/csv",
    )
