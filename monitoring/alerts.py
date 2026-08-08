"""
alerts.py
----------
Threshold-based alerting for Resolvix-AI.

Watches health checks and key metrics, and dispatches notifications
through one or more configured channels (Slack webhook, email, generic
webhook) when a condition is breached. Includes basic de-duplication
/ cooldown so the same alert doesn't spam a channel every polling cycle.

Usage:
    from monitoring.alerts import AlertManager, AlertSeverity

    alert_manager = AlertManager()
    alert_manager.add_channel(SlackChannel(webhook_url="https://hooks.slack.com/..."))
    alert_manager.add_channel(EmailChannel(smtp_host="smtp.example.com", ...))

    await alert_manager.fire(
        title="Fraud detection queue backed up",
        message="47 complaints pending fraud review, oldest is 40 minutes old",
        severity=AlertSeverity.WARNING,
        source="fraud_agent",
    )

    # Or run periodic threshold checks:
    await alert_manager.evaluate_health(health_checker)
"""

import asyncio
import json
import smtplib
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from email.mime.text import MIMEText
from enum import Enum
from typing import Dict, List, Optional

import urllib.request
import urllib.error

from monitoring.logging import get_logger

logger = get_logger(__name__)


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Alert:
    title: str
    message: str
    severity: AlertSeverity
    source: str
    timestamp: float = field(default_factory=time.time)
    details: Dict = field(default_factory=dict)

    def fingerprint(self) -> str:
        """Used for de-duplication — same source+title within cooldown is suppressed."""
        return f"{self.source}:{self.title}"


# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------
class AlertChannel(ABC):
    @abstractmethod
    async def send(self, alert: Alert) -> None:
        ...


class SlackChannel(AlertChannel):
    def __init__(self, webhook_url: str, min_severity: AlertSeverity = AlertSeverity.WARNING):
        self.webhook_url = webhook_url
        self.min_severity = min_severity

    _SEVERITY_ORDER = {AlertSeverity.INFO: 0, AlertSeverity.WARNING: 1, AlertSeverity.CRITICAL: 2}
    _EMOJI = {AlertSeverity.INFO: "ℹ️", AlertSeverity.WARNING: "⚠️", AlertSeverity.CRITICAL: "🚨"}

    async def send(self, alert: Alert) -> None:
        if self._SEVERITY_ORDER[alert.severity] < self._SEVERITY_ORDER[self.min_severity]:
            return

        payload = {
            "text": f"{self._EMOJI[alert.severity]} *{alert.title}*\n"
                    f"{alert.message}\n"
                    f"_source: {alert.source} | severity: {alert.severity.value}_"
        }

        def _post():
            req = urllib.request.Request(
                self.webhook_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                urllib.request.urlopen(req, timeout=5)
            except urllib.error.URLError as exc:
                logger.error("Failed to send Slack alert", extra={"error": str(exc)})

        await asyncio.get_event_loop().run_in_executor(None, _post)


class WebhookChannel(AlertChannel):
    """Generic JSON webhook, e.g. for PagerDuty, Opsgenie, or an internal endpoint."""

    def __init__(self, url: str, headers: Optional[Dict[str, str]] = None):
        self.url = url
        self.headers = headers or {"Content-Type": "application/json"}

    async def send(self, alert: Alert) -> None:
        payload = {
            "title": alert.title,
            "message": alert.message,
            "severity": alert.severity.value,
            "source": alert.source,
            "timestamp": alert.timestamp,
            "details": alert.details,
        }

        def _post():
            req = urllib.request.Request(
                self.url,
                data=json.dumps(payload).encode("utf-8"),
                headers=self.headers,
                method="POST",
            )
            try:
                urllib.request.urlopen(req, timeout=5)
            except urllib.error.URLError as exc:
                logger.error("Failed to send webhook alert", extra={"error": str(exc)})

        await asyncio.get_event_loop().run_in_executor(None, _post)


class EmailChannel(AlertChannel):
    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        username: str,
        password: str,
        from_addr: str,
        to_addrs: List[str],
        min_severity: AlertSeverity = AlertSeverity.CRITICAL,
        use_tls: bool = True,
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_addr = from_addr
        self.to_addrs = to_addrs
        self.min_severity = min_severity
        self.use_tls = use_tls

    _SEVERITY_ORDER = {AlertSeverity.INFO: 0, AlertSeverity.WARNING: 1, AlertSeverity.CRITICAL: 2}

    async def send(self, alert: Alert) -> None:
        if self._SEVERITY_ORDER[alert.severity] < self._SEVERITY_ORDER[self.min_severity]:
            return

        def _send_email():
            msg = MIMEText(f"{alert.message}\n\nSource: {alert.source}\nSeverity: {alert.severity.value}")
            msg["Subject"] = f"[Resolvix-AI] {alert.severity.value.upper()}: {alert.title}"
            msg["From"] = self.from_addr
            msg["To"] = ", ".join(self.to_addrs)

            try:
                with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:
                    if self.use_tls:
                        server.starttls()
                    server.login(self.username, self.password)
                    server.sendmail(self.from_addr, self.to_addrs, msg.as_string())
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to send email alert", extra={"error": str(exc)})

        await asyncio.get_event_loop().run_in_executor(None, _send_email)


class LogChannel(AlertChannel):
    """Fallback channel — always logs the alert. Useful in dev or as a baseline."""

    async def send(self, alert: Alert) -> None:
        log_fn = {
            AlertSeverity.INFO: logger.info,
            AlertSeverity.WARNING: logger.warning,
            AlertSeverity.CRITICAL: logger.error,
        }[alert.severity]
        log_fn(f"ALERT: {alert.title}", extra={"alert_message": alert.message, "source": alert.source})


# ---------------------------------------------------------------------------
# Alert manager
# ---------------------------------------------------------------------------
class AlertManager:
    def __init__(self, cooldown_seconds: int = 900):
        self.channels: List[AlertChannel] = [LogChannel()]
        self.cooldown_seconds = cooldown_seconds
        self._last_sent: Dict[str, float] = {}

    def add_channel(self, channel: AlertChannel) -> None:
        self.channels.append(channel)

    def _in_cooldown(self, alert: Alert) -> bool:
        fp = alert.fingerprint()
        last = self._last_sent.get(fp)
        if last is not None and (time.time() - last) < self.cooldown_seconds:
            return True
        return False

    async def fire(
        self,
        title: str,
        message: str,
        severity: AlertSeverity = AlertSeverity.WARNING,
        source: str = "system",
        details: Optional[Dict] = None,
    ) -> None:
        alert = Alert(title=title, message=message, severity=severity, source=source, details=details or {})

        if self._in_cooldown(alert):
            logger.info("Alert suppressed (cooldown)", extra={"title": title, "source": source})
            return

        self._last_sent[alert.fingerprint()] = time.time()

        await asyncio.gather(
            *(channel.send(alert) for channel in self.channels),
            return_exceptions=True,
        )

    # ------------------------------------------------------------------
    # Threshold evaluation helpers
    # ------------------------------------------------------------------
    async def evaluate_health(self, health_result: Dict) -> None:
        """
        Feed the dict returned by HealthChecker.run_all() and fire alerts
        for any unhealthy or degraded dependency.
        """
        for check in health_result.get("checks", []):
            if check["status"] == "unhealthy":
                await self.fire(
                    title=f"{check['name']} is unhealthy",
                    message=check.get("message", "No details provided"),
                    severity=AlertSeverity.CRITICAL,
                    source=check["name"],
                    details=check.get("details", {}),
                )
            elif check["status"] == "degraded":
                await self.fire(
                    title=f"{check['name']} is degraded",
                    message=check.get("message", "No details provided"),
                    severity=AlertSeverity.WARNING,
                    source=check["name"],
                    details=check.get("details", {}),
                )

    async def evaluate_threshold(
        self,
        metric_name: str,
        current_value: float,
        warning_threshold: Optional[float] = None,
        critical_threshold: Optional[float] = None,
        source: str = "metrics",
        comparison: str = "greater_than",  # or "less_than"
    ) -> None:
        """Generic helper for firing an alert when a metric crosses a threshold."""

        def breached(value: float, threshold: float) -> bool:
            return value > threshold if comparison == "greater_than" else value < threshold

        if critical_threshold is not None and breached(current_value, critical_threshold):
            await self.fire(
                title=f"{metric_name} breached critical threshold",
                message=f"{metric_name} = {current_value} (threshold: {critical_threshold})",
                severity=AlertSeverity.CRITICAL,
                source=source,
            )
        elif warning_threshold is not None and breached(current_value, warning_threshold):
            await self.fire(
                title=f"{metric_name} breached warning threshold",
                message=f"{metric_name} = {current_value} (threshold: {warning_threshold})",
                severity=AlertSeverity.WARNING,
                source=source,
            )


# Singleton for convenience — configure channels at app startup
alert_manager = AlertManager()
