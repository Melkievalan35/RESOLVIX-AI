"""
metrics.py
-----------
Centralized metrics collection for Resolvix-AI.

Exposes Prometheus-compatible metrics for:
    - API request latency / throughput / error rate
    - AI agent execution (orchestrator, fraud, resolution, etc.)
    - RAG pipeline performance (retrieval latency, chunk counts)
    - Complaint lifecycle (created, resolved, escalated)
    - System resource usage

Usage:
    from monitoring.metrics import metrics

    # In FastAPI middleware:
    metrics.track_request("POST", "/api/complaints", 200, 0.145)

    # In an agent:
    with metrics.track_agent("fraud_agent"):
        result = fraud_agent.run(complaint)

    # Expose /metrics endpoint:
    from monitoring.metrics import metrics_endpoint
    app.add_route("/metrics", metrics_endpoint)
"""

import time
import logging
from contextlib import contextmanager
from typing import Optional

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
)

logger = logging.getLogger("resolvix.metrics")

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
REGISTRY = CollectorRegistry()

# ---------------------------------------------------------------------------
# API-level metrics
# ---------------------------------------------------------------------------
HTTP_REQUESTS_TOTAL = Counter(
    "resolvix_http_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status_code"],
    registry=REGISTRY,
)

HTTP_REQUEST_DURATION = Histogram(
    "resolvix_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
    registry=REGISTRY,
)

HTTP_ERRORS_TOTAL = Counter(
    "resolvix_http_errors_total",
    "Total number of HTTP 4xx/5xx responses",
    ["method", "endpoint", "status_code"],
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# AI agent metrics
# ---------------------------------------------------------------------------
AGENT_INVOCATIONS_TOTAL = Counter(
    "resolvix_agent_invocations_total",
    "Total number of times an AI agent was invoked",
    ["agent_name", "status"],
    registry=REGISTRY,
)

AGENT_EXECUTION_DURATION = Histogram(
    "resolvix_agent_execution_duration_seconds",
    "Execution time of an AI agent",
    ["agent_name"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60),
    registry=REGISTRY,
)

AGENT_CONFIDENCE_SCORE = Histogram(
    "resolvix_agent_confidence_score",
    "Confidence score returned by an agent decision",
    ["agent_name"],
    buckets=(0.1, 0.3, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0),
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# RAG pipeline metrics
# ---------------------------------------------------------------------------
RAG_RETRIEVAL_DURATION = Histogram(
    "resolvix_rag_retrieval_duration_seconds",
    "Time taken to retrieve chunks from the vector store",
    ["stage"],  # embedding | vector_search | rerank | generate
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
    registry=REGISTRY,
)

RAG_CHUNKS_RETRIEVED = Histogram(
    "resolvix_rag_chunks_retrieved",
    "Number of chunks retrieved per query",
    buckets=(1, 2, 3, 5, 8, 10, 15, 20),
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Fraud detection metrics
# ---------------------------------------------------------------------------
FRAUD_SCORE_DISTRIBUTION = Histogram(
    "resolvix_fraud_score",
    "Distribution of fraud scores assigned to complaints",
    buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
    registry=REGISTRY,
)

FRAUD_FLAGGED_TOTAL = Counter(
    "resolvix_fraud_flagged_total",
    "Total number of complaints flagged as potentially fraudulent",
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Complaint lifecycle metrics
# ---------------------------------------------------------------------------
COMPLAINTS_CREATED_TOTAL = Counter(
    "resolvix_complaints_created_total",
    "Total number of complaints submitted",
    ["category"],
    registry=REGISTRY,
)

COMPLAINTS_RESOLVED_TOTAL = Counter(
    "resolvix_complaints_resolved_total",
    "Total number of complaints resolved",
    ["resolution_type"],  # auto | manual | escalated
    registry=REGISTRY,
)

COMPLAINTS_ESCALATED_TOTAL = Counter(
    "resolvix_complaints_escalated_total",
    "Total number of complaints escalated to a human agent",
    ["reason"],
    registry=REGISTRY,
)

COMPLAINT_RESOLUTION_TIME = Histogram(
    "resolvix_complaint_resolution_seconds",
    "Time from complaint creation to resolution",
    buckets=(60, 300, 900, 3600, 21600, 86400, 259200),  # 1m .. 3d
    registry=REGISTRY,
)

ACTIVE_COMPLAINTS = Gauge(
    "resolvix_active_complaints",
    "Number of complaints currently open",
    ["status"],
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# System / infra metrics
# ---------------------------------------------------------------------------
VECTOR_DB_SIZE = Gauge(
    "resolvix_vector_db_documents",
    "Number of documents currently indexed in the vector store",
    registry=REGISTRY,
)

LLM_TOKENS_TOTAL = Counter(
    "resolvix_llm_tokens_total",
    "Total tokens consumed by LLM calls",
    ["model", "type"],  # type: prompt | completion
    registry=REGISTRY,
)

LLM_CALL_DURATION = Histogram(
    "resolvix_llm_call_duration_seconds",
    "Latency of LLM API calls",
    ["model"],
    buckets=(0.5, 1, 2, 5, 10, 20, 30, 60),
    registry=REGISTRY,
)


class MetricsRegistry:
    """High-level convenience wrapper around the raw Prometheus metrics."""

    def track_request(self, method: str, endpoint: str, status_code: int, duration: float) -> None:
        HTTP_REQUESTS_TOTAL.labels(method=method, endpoint=endpoint, status_code=status_code).inc()
        HTTP_REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)
        if status_code >= 400:
            HTTP_ERRORS_TOTAL.labels(method=method, endpoint=endpoint, status_code=status_code).inc()

    @contextmanager
    def track_agent(self, agent_name: str):
        """Context manager to time and record the outcome of an agent run."""
        start = time.perf_counter()
        status = "success"
        try:
            yield
        except Exception:
            status = "error"
            raise
        finally:
            duration = time.perf_counter() - start
            AGENT_EXECUTION_DURATION.labels(agent_name=agent_name).observe(duration)
            AGENT_INVOCATIONS_TOTAL.labels(agent_name=agent_name, status=status).inc()

    def record_agent_confidence(self, agent_name: str, score: float) -> None:
        AGENT_CONFIDENCE_SCORE.labels(agent_name=agent_name).observe(score)

    @contextmanager
    def track_rag_stage(self, stage: str):
        start = time.perf_counter()
        try:
            yield
        finally:
            RAG_RETRIEVAL_DURATION.labels(stage=stage).observe(time.perf_counter() - start)

    def record_chunks_retrieved(self, count: int) -> None:
        RAG_CHUNKS_RETRIEVED.observe(count)

    def record_fraud_score(self, score: float, flagged: bool = False) -> None:
        FRAUD_SCORE_DISTRIBUTION.observe(score)
        if flagged:
            FRAUD_FLAGGED_TOTAL.inc()

    def record_complaint_created(self, category: str = "general") -> None:
        COMPLAINTS_CREATED_TOTAL.labels(category=category).inc()

    def record_complaint_resolved(self, resolution_type: str, resolution_seconds: Optional[float] = None) -> None:
        COMPLAINTS_RESOLVED_TOTAL.labels(resolution_type=resolution_type).inc()
        if resolution_seconds is not None:
            COMPLAINT_RESOLUTION_TIME.observe(resolution_seconds)

    def record_complaint_escalated(self, reason: str = "unspecified") -> None:
        COMPLAINTS_ESCALATED_TOTAL.labels(reason=reason).inc()

    def set_active_complaints(self, status: str, count: int) -> None:
        ACTIVE_COMPLAINTS.labels(status=status).set(count)

    def set_vector_db_size(self, count: int) -> None:
        VECTOR_DB_SIZE.set(count)

    def record_llm_call(self, model: str, prompt_tokens: int, completion_tokens: int, duration: float) -> None:
        LLM_TOKENS_TOTAL.labels(model=model, type="prompt").inc(prompt_tokens)
        LLM_TOKENS_TOTAL.labels(model=model, type="completion").inc(completion_tokens)
        LLM_CALL_DURATION.labels(model=model).observe(duration)

    def export(self) -> bytes:
        """Return metrics in Prometheus text exposition format."""
        return generate_latest(REGISTRY)


# Singleton used across the codebase
metrics = MetricsRegistry()


# ---------------------------------------------------------------------------
# FastAPI integration helpers
# ---------------------------------------------------------------------------
def metrics_endpoint():
    """
    FastAPI-compatible endpoint handler.

    Example:
        from fastapi import FastAPI, Response
        app = FastAPI()

        @app.get("/metrics")
        def metrics_route():
            return Response(content=metrics.export(), media_type=CONTENT_TYPE_LATEST)
    """
    return metrics.export(), CONTENT_TYPE_LATEST


class PrometheusMiddleware:
    """
    ASGI middleware that automatically records request metrics.

    Usage (FastAPI):
        app.add_middleware(PrometheusMiddleware)
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "UNKNOWN")
        path = scope.get("path", "unknown")
        start = time.perf_counter()
        status_holder = {"code": 500}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.perf_counter() - start
            metrics.track_request(method, path, status_holder["code"], duration)
