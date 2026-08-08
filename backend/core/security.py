"""
core/security.py
------------------
Security primitives shared across the backend:

  - Password hashing / verification            -> used by api/auth.py,
                                                    authentication/*
  - JWT access & refresh token creation/decode  -> used by api/auth.py,
                                                    middleware/ (auth guard)
  - FastAPI dependencies for the current user
    and role-based access control (RBAC)        -> used by every protected
                                                    route in api/*.py

Nothing here talks to the database directly. `get_current_user` accepts a
`user_loader` callable so it stays decoupled from `database/models.py` —
wire the real loader in `authentication/` at app startup, or override the
dependency in `backend/main.py` with `app.dependency_overrides`.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from core.settings import settings

# --------------------------------------------------------------------- #
# Password hashing
# --------------------------------------------------------------------- #
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password for storage (database/models.py User.password_hash)."""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against its stored bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


# --------------------------------------------------------------------- #
# JWT tokens
# --------------------------------------------------------------------- #
class TokenPayload(BaseModel):
    sub: str  # user id
    role: str
    type: str  # "access" | "refresh"
    exp: datetime


def _create_token(subject: str, role: str, token_type: str, expires_delta: timedelta) -> str:
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode = {"sub": str(subject), "role": role, "type": token_type, "exp": expire}
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(subject: str, role: str) -> str:
    """Issue a short-lived access token. Consumed by api/auth.py on login."""
    return _create_token(
        subject, role, "access",
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(subject: str, role: str) -> str:
    """Issue a longer-lived refresh token. Consumed by api/auth.py refresh endpoint."""
    return _create_token(
        subject, role, "refresh",
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str) -> TokenPayload:
    """
    Decode and validate a JWT. Raises HTTPException(401) on any failure
    (expired, malformed, bad signature) so callers can just propagate it.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return TokenPayload(**payload)
    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


# --------------------------------------------------------------------- #
# FastAPI auth dependencies
# --------------------------------------------------------------------- #
# tokenUrl points at the login route exposed by api/auth.py
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login"
)

class CurrentUser(BaseModel):
    """Lightweight identity extracted from a validated access token."""
    id: str
    role: str


def get_current_user(token: str = Depends(oauth2_scheme)) -> CurrentUser:
    """
    Base dependency used across api/*.py, e.g.:

        @router.get("/complaints/{id}")
        def get_complaint(id: str, user: CurrentUser = Depends(get_current_user)):
            ...

    For endpoints that need the full DB-backed user record (not just id +
    role), wrap this dependency in authentication/ with a lookup against
    database/models.py, e.g.:

        def get_current_db_user(user: CurrentUser = Depends(get_current_user)):
            return user_repository.get_by_id(user.id)
    """
    payload = decode_token(token)
    if payload.type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type; access token required",
        )
    return CurrentUser(id=payload.sub, role=payload.role)


def require_roles(*allowed_roles: str) -> Callable[[CurrentUser], CurrentUser]:
    """
    RBAC dependency factory. Use on any route that should be restricted to
    specific roles (admin-dashboard endpoints, audit log access, etc.):

        @router.get("/admin/fraud-analytics")
        def fraud_analytics(
            user: CurrentUser = Depends(require_roles(settings.ROLE_ADMIN, settings.ROLE_AUDITOR))
        ):
            ...
    """

    def dependency(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return current_user

    return dependency


# Convenience pre-built dependencies for the four platform roles
REFRESH_TOKEN_EXPIRE_DAYS: int = 7
require_admin = require_roles(settings.ROLE_ADMIN)
require_agent_or_admin = require_roles(settings.ROLE_AGENT, settings.ROLE_ADMIN)
require_auditor = require_roles(settings.ROLE_AUDITOR, settings.ROLE_ADMIN)
require_customer = require_roles(settings.ROLE_CUSTOMER)
