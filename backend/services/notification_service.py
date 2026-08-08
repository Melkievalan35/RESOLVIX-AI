"""
Notification service.

Centralizes creation and delivery of notifications so that any part of
the system (complaint updates, workflow transitions, fraud alerts) can
notify a user through one consistent path. Routers should call this
instead of constructing Notification rows directly.
"""
from typing import Iterable, List, Optional

from sqlalchemy.orm import Session

from database.models import Notification, NotificationType, User


def notify_user(
    db: Session,
    user_id: str,
    message: str,
    notif_type: NotificationType = NotificationType.INFO,
    related_complaint_id: Optional[str] = None,
    commit: bool = True,
) -> Notification:
    """Create a single notification for one user."""
    notification = Notification(
        user_id=user_id,
        message=message,
        type=notif_type,
        related_complaint_id=related_complaint_id,
    )
    db.add(notification)
    if commit:
        db.commit()
        db.refresh(notification)
    return notification


def notify_many(
    db: Session,
    user_ids: Iterable[str],
    message: str,
    notif_type: NotificationType = NotificationType.INFO,
    related_complaint_id: Optional[str] = None,
) -> List[Notification]:
    """Create the same notification for several users (e.g. all admins)."""
    notifications = [
        Notification(
            user_id=uid,
            message=message,
            type=notif_type,
            related_complaint_id=related_complaint_id,
        )
        for uid in user_ids
    ]
    db.add_all(notifications)
    db.commit()
    for n in notifications:
        db.refresh(n)
    return notifications


def notify_admins_and_agents(
    db: Session,
    message: str,
    notif_type: NotificationType = NotificationType.INFO,
    related_complaint_id: Optional[str] = None,
) -> List[Notification]:
    """Broadcast to every agent and admin — used for escalations and fraud alerts."""
    from database.models import UserRole  # local import avoids a circular import at module load

    staff_ids = [
        u.id for u in db.query(User).filter(User.role.in_([UserRole.AGENT, UserRole.ADMIN])).all()
    ]
    return notify_many(db, staff_ids, message, notif_type, related_complaint_id)


def notify_status_change(db: Session, complaint, old_status: str, new_status: str) -> Notification:
    """Notify the complaint's customer that their case status changed."""
    message = f"Your complaint '{complaint.title}' status changed from {old_status} to {new_status}."
    return notify_user(
        db,
        user_id=complaint.customer_id,
        message=message,
        notif_type=NotificationType.STATUS_UPDATE,
        related_complaint_id=complaint.id,
    )


def notify_fraud_alert(db: Session, complaint) -> List[Notification]:
    """Alert staff when a complaint's fraud score crosses the review threshold."""
    message = f"Fraud alert: complaint '{complaint.title}' scored {complaint.fraud_score:.2f}."
    return notify_admins_and_agents(
        db, message, notif_type=NotificationType.FRAUD_ALERT, related_complaint_id=complaint.id
    )


def notify_escalation(db: Session, complaint) -> List[Notification]:
    """Alert staff when a complaint is escalated."""
    message = f"Complaint '{complaint.title}' has been escalated and needs attention."
    return notify_admins_and_agents(
        db, message, notif_type=NotificationType.ESCALATION, related_complaint_id=complaint.id
    )


def list_notifications(db: Session, user_id: str, unread_only: bool = False) -> List[Notification]:
    query = db.query(Notification).filter(Notification.user_id == user_id)
    if unread_only:
        query = query.filter(Notification.is_read.is_(False))
    return query.order_by(Notification.created_at.desc()).all()


def mark_read(db: Session, notification_id: str, user_id: str) -> Optional[Notification]:
    notification = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == user_id)
        .first()
    )
    if not notification:
        return None
    notification.is_read = True
    db.commit()
    db.refresh(notification)
    return notification


def mark_all_read(db: Session, user_id: str) -> int:
    updated = (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.is_read.is_(False))
        .update({Notification.is_read: True})
    )
    db.commit()
    return updated


def delete_notification(db: Session, notification_id: str, user_id: str) -> bool:
    notification = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == user_id)
        .first()
    )
    if not notification:
        return False
    db.delete(notification)
    db.commit()
    return True
