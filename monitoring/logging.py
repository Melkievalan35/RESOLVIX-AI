"""
logging.py
-----------
Centralized structured logging for Resolvix-AI.

Features:
    - JSON-formatted logs (production) or colored console logs (development)
    - Rotating file handler for persistent logs under storage/logs/
    - Request-scoped context (request_id, user_id) via contextvars
    - Convenience helpers for logging agent decisions and audit events

Usage:
    from monitoring.logging import setup_logging, get_logger, log_context

    setup_logging(env="production", log_dir="storage/logs")
    logger = get_logger(__name__)

    with log_context(request_id="abc123", user_id="u_42"):
        logger.info("Complaint created", extra={"complaint_id": "c_991"})
"""

import json
import logging
import logging.handlers
import os
import sys
import contextvars
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Request-scoped context
# ---------------------------------------------------------------------------
_request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
_user_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("user_id", default="-")


class log_context:
    """Context manager to attach request-scoped fields to all logs emitted within it."""

    def __init__(self, request_id: Optional[str] = None, user_id: Optional[str] = None):
        self.request_id = request_id
        self.user_id = user_id
        self._tokens = []

    def __enter__(self):
        if self.request_id is not None:
            self._tokens.append((_request_id_ctx, _request_id_ctx.set(self.request_id)))
        if self.user_id is not None:
            self._tokens.append((_user_id_ctx, _user_id_ctx.set(self.user_id)))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        for var, token in self._tokens:
            var.reset(token)


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------
class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON, suitable for log aggregators."""

    RESERVED = {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "message",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "request_id": _request_id_ctx.get(),
            "user_id": _user_id_ctx.get(),
        }

        # Include any custom fields passed via `extra=`
        for key, value in record.__dict__.items():
            if key not in self.RESERVED and key not in payload and not key.startswith("_"):
                try:
                    json.dumps(value)
                    payload[key] = value
                except (TypeError, ValueError):
                    payload[key] = str(value)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


class ConsoleFormatter(logging.Formatter):
    """Human-readable, colorized formatter for local development."""

    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[41m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        ts = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        req_id = _request_id_ctx.get()
        base = f"{color}[{ts}] {record.levelname:<8}{self.RESET} {record.name} — {record.getMessage()}"
        if req_id != "-":
            base += f"  (request_id={req_id})"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
def setup_logging(
    env: str = "development",
    log_dir: str = "storage/logs",
    log_level: str = "INFO",
    max_bytes: int = 25 * 1024 * 1024,  # 25 MB
    backup_count: int = 10,
) -> None:
    """
    Configure root logging for the whole application.

    Call this once at startup (e.g. in backend/main.py).
    """
    root = logging.getLogger()
    root.setLevel(log_level.upper())
    root.handlers.clear()

    formatter = JSONFormatter() if env == "production" else ConsoleFormatter()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    # Rotating file handler (always JSON, regardless of env, for durability)
    os.makedirs(log_dir, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        filename=os.path.join(log_dir, "resolvix.log"),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(JSONFormatter())
    root.addHandler(file_handler)

    # Separate error-only file for quick triage
    error_handler = logging.handlers.RotatingFileHandler(
        filename=os.path.join(log_dir, "resolvix.error.log"),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(JSONFormatter())
    root.addHandler(error_handler)

    # Quiet noisy third-party loggers
    for noisy in ("urllib3", "httpx", "asyncio", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger("resolvix").info(
        "Logging initialized", extra={"env": env, "log_dir": log_dir, "log_level": log_level}
    )


def get_logger(name: str) -> logging.Logger:
    """Standard way to obtain a module-level logger across the codebase."""
    return logging.getLogger(name)


# ---------------------------------------------------------------------------
# Domain-specific convenience loggers
# ---------------------------------------------------------------------------
_audit_logger = logging.getLogger("resolvix.audit")
_agent_logger = logging.getLogger("resolvix.agent")


def log_audit_event(action: str, actor: str, target: str, details: Optional[Dict[str, Any]] = None) -> None:
    """
    Log an audit-trail event (e.g. admin actions, complaint status changes).
    Mirrors what would be persisted to the audit_logs table.
    """
    _audit_logger.info(
        "audit_event",
        extra={
            "audit_action": action,
            "actor": actor,
            "target": target,
            "details": details or {},
        },
    )


def log_agent_decision(
    agent_name: str,
    complaint_id: str,
    decision: str,
    confidence: Optional[float] = None,
    reasoning: Optional[str] = None,
) -> None:
    """Log an AI agent's decision for explainability / audit purposes."""
    _agent_logger.info(
        "agent_decision",
        extra={
            "agent_name": agent_name,
            "complaint_id": complaint_id,
            "decision": decision,
            "confidence": confidence,
            "reasoning": reasoning,
        },
    )
