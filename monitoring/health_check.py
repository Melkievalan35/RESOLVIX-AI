"""
health_check.py
-----------------
Liveness / readiness checks for Resolvix-AI's dependencies.

Checks:
    - Database connectivity (Postgres/MySQL via SQLAlchemy)
    - Vector store connectivity (e.g. Chroma / Pinecone / Weaviate)
    - LLM provider reachability
    - Redis / cache (if used)
    - Disk space on storage volumes

Usage (FastAPI):
    from fastapi import FastAPI
    from monitoring.health_check import HealthChecker

    app = FastAPI()
    checker = HealthChecker()

    @app.get("/health/live")
    async def liveness():
        return {"status": "ok"}

    @app.get("/health/ready")
    async def readiness():
        result = await checker.run_all()
        status_code = 200 if result["status"] == "healthy" else 503
        return JSONResponse(content=result, status_code=status_code)
"""

import asyncio
import shutil
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Awaitable, Dict, List, Optional

from monitoring.logging import get_logger

logger = get_logger(__name__)


class Status(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class CheckResult:
    name: str
    status: Status
    latency_ms: float
    message: str = ""
    details: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "status": self.status.value,
            "latency_ms": round(self.latency_ms, 2),
            "message": self.message,
            "details": self.details,
        }


class HealthChecker:
    """
    Registry of async health checks. Add checks with `register`, then
    call `run_all` to execute them concurrently and aggregate a result.
    """

    def __init__(self, timeout_seconds: float = 5.0):
        self.timeout_seconds = timeout_seconds
        self._checks: Dict[str, Callable[[], Awaitable[CheckResult]]] = {}
        self._register_defaults()

    def register(self, name: str, check_fn: Callable[[], Awaitable[CheckResult]]) -> None:
        self._checks[name] = check_fn

    def _register_defaults(self) -> None:
        self.register("database", self.check_database)
        self.register("vector_store", self.check_vector_store)
        self.register("llm_provider", self.check_llm_provider)
        self.register("redis", self.check_redis)
        self.register("disk_space", self.check_disk_space)

    async def _run_one(self, name: str, fn: Callable[[], Awaitable[CheckResult]]) -> CheckResult:
        start = time.perf_counter()
        try:
            result = await asyncio.wait_for(fn(), timeout=self.timeout_seconds)
            return result
        except asyncio.TimeoutError:
            return CheckResult(
                name=name,
                status=Status.UNHEALTHY,
                latency_ms=(time.perf_counter() - start) * 1000,
                message=f"Check timed out after {self.timeout_seconds}s",
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Health check failed", extra={"check": name, "error": str(exc)})
            return CheckResult(
                name=name,
                status=Status.UNHEALTHY,
                latency_ms=(time.perf_counter() - start) * 1000,
                message=str(exc),
            )

    async def run_all(self, only: Optional[List[str]] = None) -> Dict:
        """Run all (or a subset of) registered checks concurrently."""
        checks = {k: v for k, v in self._checks.items() if only is None or k in only}
        results = await asyncio.gather(*(self._run_one(name, fn) for name, fn in checks.items()))

        overall = Status.HEALTHY
        for r in results:
            if r.status == Status.UNHEALTHY:
                overall = Status.UNHEALTHY
                break
            if r.status == Status.DEGRADED:
                overall = Status.DEGRADED

        return {
            "status": overall.value,
            "timestamp": time.time(),
            "checks": [r.to_dict() for r in results],
        }

    # ------------------------------------------------------------------
    # Individual checks — wire these up to your actual clients
    # ------------------------------------------------------------------
    async def check_database(self) -> CheckResult:
        start = time.perf_counter()
        try:
            from backend.database.connection import get_engine  # local import avoids hard dependency

            engine = get_engine()
            with engine.connect() as conn:
                conn.exec_driver_sql("SELECT 1")
            return CheckResult(
                name="database",
                status=Status.HEALTHY,
                latency_ms=(time.perf_counter() - start) * 1000,
                message="Connected",
            )
        except ImportError:
            return CheckResult(
                name="database",
                status=Status.DEGRADED,
                latency_ms=(time.perf_counter() - start) * 1000,
                message="Database module not wired up yet",
            )
        except Exception as exc:  # noqa: BLE001
            return CheckResult(
                name="database",
                status=Status.UNHEALTHY,
                latency_ms=(time.perf_counter() - start) * 1000,
                message=str(exc),
            )

    async def check_vector_store(self) -> CheckResult:
        start = time.perf_counter()
        try:
            from ai.rag.vectordb import get_client  # expected factory in vectordb.py

            client = get_client()
            count = client.count() if hasattr(client, "count") else None
            return CheckResult(
                name="vector_store",
                status=Status.HEALTHY,
                latency_ms=(time.perf_counter() - start) * 1000,
                message="Connected",
                details={"document_count": count} if count is not None else {},
            )
        except ImportError:
            return CheckResult(
                name="vector_store",
                status=Status.DEGRADED,
                latency_ms=(time.perf_counter() - start) * 1000,
                message="Vector store module not wired up yet",
            )
        except Exception as exc:  # noqa: BLE001
            return CheckResult(
                name="vector_store",
                status=Status.UNHEALTHY,
                latency_ms=(time.perf_counter() - start) * 1000,
                message=str(exc),
            )

    async def check_llm_provider(self) -> CheckResult:
        start = time.perf_counter()
        try:
            from ai.llm.model_loader import ping  # expected lightweight ping/model-list call

            await ping() if asyncio.iscoroutinefunction(ping) else ping()
            return CheckResult(
                name="llm_provider",
                status=Status.HEALTHY,
                latency_ms=(time.perf_counter() - start) * 1000,
                message="Reachable",
            )
        except ImportError:
            return CheckResult(
                name="llm_provider",
                status=Status.DEGRADED,
                latency_ms=(time.perf_counter() - start) * 1000,
                message="LLM module not wired up yet",
            )
        except Exception as exc:  # noqa: BLE001
            return CheckResult(
                name="llm_provider",
                status=Status.UNHEALTHY,
                latency_ms=(time.perf_counter() - start) * 1000,
                message=str(exc),
            )

    async def check_redis(self) -> CheckResult:
        start = time.perf_counter()
        try:
            import redis.asyncio as redis  # optional dependency
            import os

            client = redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
            await client.ping()
            await client.close()
            return CheckResult(
                name="redis",
                status=Status.HEALTHY,
                latency_ms=(time.perf_counter() - start) * 1000,
                message="Connected",
            )
        except ImportError:
            return CheckResult(
                name="redis",
                status=Status.DEGRADED,
                latency_ms=(time.perf_counter() - start) * 1000,
                message="redis package not installed / not used",
            )
        except Exception as exc:  # noqa: BLE001
            return CheckResult(
                name="redis",
                status=Status.UNHEALTHY,
                latency_ms=(time.perf_counter() - start) * 1000,
                message=str(exc),
            )

    async def check_disk_space(self, path: str = "storage", warn_threshold_pct: float = 85.0) -> CheckResult:
        start = time.perf_counter()
        try:
            total, used, free = shutil.disk_usage(path)
            used_pct = (used / total) * 100
            status = Status.HEALTHY
            message = "OK"
            if used_pct >= 95:
                status = Status.UNHEALTHY
                message = "Disk space critically low"
            elif used_pct >= warn_threshold_pct:
                status = Status.DEGRADED
                message = "Disk space running low"

            return CheckResult(
                name="disk_space",
                status=status,
                latency_ms=(time.perf_counter() - start) * 1000,
                message=message,
                details={
                    "used_percent": round(used_pct, 1),
                    "free_gb": round(free / (1024 ** 3), 2),
                    "total_gb": round(total / (1024 ** 3), 2),
                },
            )
        except Exception as exc:  # noqa: BLE001
            return CheckResult(
                name="disk_space",
                status=Status.UNHEALTHY,
                latency_ms=(time.perf_counter() - start) * 1000,
                message=str(exc),
            )
