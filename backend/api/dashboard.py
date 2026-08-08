"""
Dashboard and analytics endpoints.
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from core.security import get_current_user, require_roles
from database.connection import get_db
from database.models import (
    Complaint,
    ComplaintStatus,
    User,
    UserRole,
)
from database.schemas import DashboardSummary, StatusCount


router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"],
)


# ==========================================================
# CUSTOMER DASHBOARD
# ==========================================================

@router.get("/summary")
def get_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Dashboard summary for the currently logged-in user.
    """

    # ------------------------------------------------------
    # Customer complaints
    # ------------------------------------------------------

    query = db.query(Complaint)

    # Customers only see their own complaints.
    if current_user.role == UserRole.CUSTOMER:
        query = query.filter(
            Complaint.customer_id == current_user.id
        )

    total = query.count()

    resolved = query.filter(
        Complaint.status == ComplaintStatus.RESOLVED
    ).count()

    escalated = query.filter(
        Complaint.status == ComplaintStatus.ESCALATED
    ).count()

    open_count = query.filter(
        Complaint.status.in_(
            [
                ComplaintStatus.SUBMITTED,
                ComplaintStatus.OPEN,
            ]
        )
    ).count()

    high_fraud = query.filter(
        Complaint.fraud_score >= 0.7
    ).count()

    # ------------------------------------------------------
    # Resolved today
    # ------------------------------------------------------

    today = datetime.utcnow().date()

    resolved_today = (
        query.filter(
            Complaint.status == ComplaintStatus.RESOLVED,
            func.date(Complaint.resolved_at) == today,
        ).count()
    )

    # ------------------------------------------------------
    # Auto resolution
    # ------------------------------------------------------

    auto_resolved = query.filter(
        Complaint.is_auto_resolved == True
    ).count()

    auto_resolution_rate = (
        round((auto_resolved / total) * 100, 2)
        if total > 0
        else 0
    )

    # ------------------------------------------------------
    # SLA breaches
    # ------------------------------------------------------

    sla_breaches = 0

    complaints = query.all()

    now = datetime.utcnow()

    for complaint in complaints:

        if (
            complaint.sla_due_at
            and complaint.sla_due_at < now
            and complaint.status != ComplaintStatus.RESOLVED
        ):
            sla_breaches += 1

    # ------------------------------------------------------
    # Status breakdown
    # ------------------------------------------------------

    breakdown = []

    for status in ComplaintStatus:

        count = query.filter(
            Complaint.status == status
        ).count()

        if count > 0:
            breakdown.append(
                {
                    "status": status.value,
                    "count": count,
                }
            )

    return {
        "total_complaints": total,
        "open_complaints": open_count,
        "resolved_complaints": resolved,
        "resolved_today": resolved_today,
        "escalated_complaints": escalated,
        "sla_breaches": sla_breaches,
        "auto_resolution_rate": auto_resolution_rate,
        "high_fraud_count": high_fraud,
        "status_breakdown": breakdown,
    }


# ==========================================================
# TRENDS
# ==========================================================

@router.get("/trends")
def get_trends(
    days: int = Query(
        14,
        ge=1,
        le=90,
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    since = datetime.utcnow() - timedelta(days=days)

    query = db.query(
        func.date(Complaint.created_at),
        func.count(Complaint.id),
    ).filter(
        Complaint.created_at >= since
    )

    if current_user.role == UserRole.CUSTOMER:
        query = query.filter(
            Complaint.customer_id == current_user.id
        )

    rows = (
        query
        .group_by(func.date(Complaint.created_at))
        .order_by(func.date(Complaint.created_at))
        .all()
    )

    return {
        "days": days,
        "data": [
            {
                "date": str(date),
                "count": count,
            }
            for date, count in rows
        ],
    }


# ==========================================================
# ADMIN FRAUD ANALYTICS
# ==========================================================

@router.get("/fraud-analytics")
def get_fraud_analytics(
    threshold: float = Query(
        0.5,
        ge=0.0,
        le=1.0,
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.ADMIN)
    ),
):

    flagged = (
        db.query(Complaint)
        .filter(
            Complaint.fraud_score >= threshold
        )
        .order_by(
            Complaint.fraud_score.desc()
        )
        .limit(100)
        .all()
    )

    return {
        "threshold": threshold,
        "flagged_count": len(flagged),
        "complaints": [
            {
                "id": c.id,
                "title": c.title,
                "fraud_score": c.fraud_score,
                "status": c.status.value,
                "created_at": c.created_at,
            }
            for c in flagged
        ],
    }


# ==========================================================
# ADMIN AGENT PERFORMANCE
# ==========================================================

@router.get("/agent-performance")
def get_agent_performance(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.ADMIN)
    ),
):

    agents = (
        db.query(User)
        .filter(User.role == UserRole.AGENT)
        .all()
    )

    performance = []

    for agent in agents:

        assigned = (
            db.query(func.count(Complaint.id))
            .filter(
                Complaint.assigned_agent_id
                == agent.id
            )
            .scalar()
            or 0
        )

        resolved = (
            db.query(func.count(Complaint.id))
            .filter(
                Complaint.assigned_agent_id
                == agent.id,
                Complaint.status
                == ComplaintStatus.RESOLVED,
            )
            .scalar()
            or 0
        )

        performance.append(
            {
                "agent_id": agent.id,
                "agent_name": agent.name,
                "assigned": assigned,
                "resolved": resolved,
                "resolution_rate": (
                    round(resolved / assigned, 2)
                    if assigned
                    else 0.0
                ),
            }
        )

    return {
        "agents": performance
    }