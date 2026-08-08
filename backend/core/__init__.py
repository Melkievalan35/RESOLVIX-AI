"""
core package
------------
Shared, dependency-free building blocks used across the whole backend:

- core.config        -> Settings (Pydantic BaseSettings) + get_settings()
- core.settings      -> singleton `settings` instance, import this everywhere else
- core.security      -> password hashing, JWT issuing/verification, RBAC dependencies
- core.dependencies  -> FastAPI Depends() functions: DB session, pagination,
                         optional-auth, plus re-exports of the auth dependencies

Import pattern used throughout the rest of the project:

    from core.settings import settings
    from core.dependencies import get_db, get_current_user, require_admin, PaginationParams
"""

from core.settings import settings  # noqa: F401
