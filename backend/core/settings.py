"""
core/settings.py
------------------
Single project-wide entrypoint for configuration.

Every other module — backend/main.py, api/*, services/*, database/*,
authentication/*, middleware/*, and the ai/* package — should do:

    from core.settings import settings

rather than importing `Settings` or `get_settings` from `core.config`
directly. This file is the one place that instantiates the settings
object, so there is exactly one source of truth at runtime.
"""

from core.config import get_settings

# Singleton instance used across the entire backend + ai packages.
settings = get_settings()

__all__ = ["settings"]
