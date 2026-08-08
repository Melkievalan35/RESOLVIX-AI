"""
core/dependencies.py
----------------------
Centralized FastAPI dependency ("Depends") functions.

Every route module in backend/api/ (auth.py, complaints.py, dashboard.py,
users.py, reports.py, notifications.py) should import what it needs from
here instead of redefining DB sessions, pagination, or auth checks
per-file. This is the single place that wires core/security.py's auth
logic together with database/connection.py's session factory.

    from core.dependencies import (
        get_db, get_current_user, require_admin,
        require_agent_or_admin, PaginationParams,
    )
"""

from typing import Generator, Optional

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from core.security import (  # noqa: F401  (re-exported for convenience)
    CurrentUser,
    get_current_user,
    require_admin,
    require_agent_or_admin,
    require_auditor,
    require_customer,
    require_roles,
)
from core.settings import settings

# --------------------------------------------------------------------- #
# Database session
# --------------------------------------------------------------------- #
# `SessionLocal` is the sessionmaker defined in backend/database/connection.py,
# built from settings.DATABASE_URL. Imported lazily/locally inside the
# function (rather than at module load) to avoid a circular import between
# core/ and database/ at package-init time.


def get_db() -> Generator[Session, None, None]:
    """
    Per-request SQLAlchemy session. Use in any route or service function
    that touches the database:

        @router.get("/complaints/{id}")
        def get_complaint(id: str, db: Session = Depends(get_db)):
            return complaint_service.get_by_id(db, id)
    """
    from database.connection import SessionLocal  # local import, avoids circularity

    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# --------------------------------------------------------------------- #
# Pagination
# --------------------------------------------------------------------- #
class PaginationParams:
    """
    Shared pagination dependency for list endpoints (complaint history,
    audit logs, reports, user management tables in admin-dashboard).

        @router.get("/complaints")
        def list_complaints(pagination: PaginationParams = Depends()):
            return complaint_service.list(
                offset=pagination.offset, limit=pagination.limit
            )
    """

    def __init__(
        self,
        page: int = Query(default=1, ge=1, description="1-indexed page number"),
        page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    ):
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


# --------------------------------------------------------------------- #
# Optional-auth (e.g. public policy search that behaves differently
# for logged-in customers vs anonymous visitors)
# --------------------------------------------------------------------- #
def get_optional_user(
    authorization: Optional[str] = None,
) -> Optional[CurrentUser]:
    """
    Best-effort current user: returns None instead of raising 401 when no
    token is supplied. Useful for endpoints in api/complaints.py or
    api/dashboard.py that are public but personalize output when
    authenticated.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1]
    try:
        from core.security import decode_token

        payload = decode_token(token)
        if payload.type != "access":
            return None
        return CurrentUser(id=payload.sub, role=payload.role)
    except Exception:
        return None


# --------------------------------------------------------------------- #
# Request-scoped app info (rarely needed directly, but handy for
# services/report_service.py when building export metadata, etc.)
# --------------------------------------------------------------------- #
def get_app_name() -> str:
    return settings.APP_NAME
