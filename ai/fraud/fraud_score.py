"""
ai/fraud/fraud_score.py

Top-level entry point for the fraud module. Combines
anomaly_detection.AnomalyDetector + behavioral_analysis.BehaviorAnalyzer
+ a small set of hard business rules into one FraudAssessment, which is
what ai/agents/fraud_agent.py should actually import and call.

This is the ONLY file other parts of the codebase need to know about:

    from ai.fraud.fraud_score import FraudScoreEngine

    engine = FraudScoreEngine()
    engine.fit_baseline(historical_feature_rows)   # once, at startup
    assessment = engine.assess(complaint, features, history, all_recent)

The returned FraudAssessment is also the shape
ai/explainable_ai/reasoning.py and audit_summary.py should consume —
its `to_dict()` / `explanation` are already judge-and-audit friendly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

try:
    from .anomaly_detection import AnomalyDetector, AnomalyResult, build_features_from_complaint
    from .behavioral_analysis import BehaviorAnalyzer, BehaviorProfile, ComplaintRecord
except ImportError:  # allows `python fraud_score.py` direct execution for quick testing
    from anomaly_detection import AnomalyDetector, AnomalyResult, build_features_from_complaint
    from behavioral_analysis import BehaviorAnalyzer, BehaviorProfile, ComplaintRecord

logger = logging.getLogger("resolvix.ai.fraud.score")


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# Default weighting between the two detectors. Exposed as a module
# constant (not hardcoded inline) so it can be tuned from a config file
# or overridden per-tenant without touching detector internals.
DEFAULT_WEIGHTS = {
    "anomaly": 0.45,
    "behavior": 0.45,
    "rules": 0.10,
}

# score thresholds -> risk level. 0-100 scale to match the
# admin-dashboard "Fraud Analytics" UI and audit_logs table.
RISK_THRESHOLDS = [
    (85, RiskLevel.CRITICAL),
    (65, RiskLevel.HIGH),
    (35, RiskLevel.MEDIUM),
    (0, RiskLevel.LOW),
]


@dataclass
class RuleHit:
    rule_id: str
    description: str
    weight: float  # 0.0 - 1.0 contribution to the rules component


@dataclass
class FraudAssessment:
    complaint_id: str
    customer_id: str
    fraud_score: float  # 0-100
    risk_level: RiskLevel
    is_flagged: bool
    anomaly_result: AnomalyResult
    behavior_profile: BehaviorProfile
    rule_hits: List[RuleHit] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def explanation(self) -> List[str]:
        """Human-readable reasons, ready for explainable_ai/reasoning.py
        and the customer-portal/admin-dashboard audit trail."""
        reasons = list(self.anomaly_result.reasons)
        reasons += list(self.behavior_profile.reasons)
        reasons += [f"Rule triggered: {r.description}" for r in self.rule_hits]
        return reasons or ["No fraud signals detected — complaint appears routine."]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "complaint_id": self.complaint_id,
            "customer_id": self.customer_id,
            "fraud_score": round(self.fraud_score, 2),
            "risk_level": self.risk_level.value,
            "is_flagged": self.is_flagged,
            "anomaly": self.anomaly_result.to_dict(),
            "behavior": self.behavior_profile.to_dict(),
            "rule_hits": [r.__dict__ for r in self.rule_hits],
            "explanation": self.explanation,
            "generated_at": self.generated_at.isoformat(),
        }


class FraudScoreEngine:
    """
    Orchestrates the two detectors + rule layer. This is what
    ai/agents/fraud_agent.py and ai/agents/orchestrator.py should hold
    a single shared instance of (fit once at process startup, reuse
    across requests — IsolationForest fitting is not cheap per-request).
    """

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        flag_threshold: float = 65.0,
    ):
        self.weights = weights or DEFAULT_WEIGHTS
        self.flag_threshold = flag_threshold
        self.anomaly_detector = AnomalyDetector()
        self.behavior_analyzer = BehaviorAnalyzer()
        self._baseline_fitted = False

    def fit_baseline(self, historical_feature_rows: List[Dict[str, float]]) -> None:
        """Call once at startup with recent historical complaint features
        (see anomaly_detection.build_features_from_complaint)."""
        self.anomaly_detector.fit(historical_feature_rows)
        self._baseline_fitted = True
        logger.info("FraudScoreEngine baseline fitted on %d rows.", len(historical_feature_rows))

    def assess(
        self,
        complaint: ComplaintRecord,
        purchase_timestamp: datetime,
        purchase_amount: float,
        customer_history: List[ComplaintRecord],
        all_recent_complaints: Optional[List[ComplaintRecord]] = None,
    ) -> FraudAssessment:
        if not self._baseline_fitted:
            logger.warning(
                "fit_baseline() was never called — using an unfitted "
                "z-score fallback with default stats. Call fit_baseline() "
                "at app startup for accurate scoring."
            )
            self.anomaly_detector.fit([])
            self._baseline_fitted = True

        last_complaint_ts = max(
            (c.created_at for c in customer_history), default=None
        )
        prior_30d = sum(
            1 for c in customer_history
            if (complaint.created_at - c.created_at).days <= 30
        )

        features = build_features_from_complaint(
            claim_amount=complaint.claim_amount,
            purchase_timestamp=purchase_timestamp,
            complaint_timestamp=complaint.created_at,
            prior_complaints_last_30_days=prior_30d,
            last_complaint_timestamp=last_complaint_ts,
            purchase_amount=purchase_amount,
        )
        anomaly_result = self.anomaly_detector.detect(features)
        behavior_profile = self.behavior_analyzer.analyze_customer(
            complaint, customer_history, all_recent_complaints
        )
        rule_hits = self._apply_rules(complaint, purchase_amount, behavior_profile)

        fraud_score = self._combine_score(anomaly_result, behavior_profile, rule_hits)
        risk_level = self._risk_level_for(fraud_score)

        return FraudAssessment(
            complaint_id=complaint.complaint_id,
            customer_id=complaint.customer_id,
            fraud_score=fraud_score,
            risk_level=risk_level,
            is_flagged=fraud_score >= self.flag_threshold,
            anomaly_result=anomaly_result,
            behavior_profile=behavior_profile,
            rule_hits=rule_hits,
        )

    # ---- internals ------------------------------------------------------

    def _apply_rules(
        self,
        complaint: ComplaintRecord,
        purchase_amount: float,
        behavior_profile: BehaviorProfile,
    ) -> List[RuleHit]:
        """Deterministic, explainable business rules — deliberately kept
        separate from the ML signals so judges/auditors can point to an
        exact reason without needing model internals."""
        hits: List[RuleHit] = []

        if purchase_amount and complaint.claim_amount >= 0.95 * purchase_amount:
            hits.append(RuleHit(
                rule_id="CLAIM_NEAR_FULL_VALUE",
                description="Claim amount is >=95% of the original purchase value",
                weight=0.5,
            ))

        if behavior_profile.shared_device_customers:
            hits.append(RuleHit(
                rule_id="MULTI_ACCOUNT_DEVICE",
                description="Same device/IP used across multiple customer accounts",
                weight=0.8,
            ))

        if behavior_profile.complaint_count_90d >= 5:
            hits.append(RuleHit(
                rule_id="SERIAL_COMPLAINANT",
                description="5+ complaints filed by this customer in the last 90 days",
                weight=0.4,
            ))

        return hits

    def _combine_score(
        self,
        anomaly_result: AnomalyResult,
        behavior_profile: BehaviorProfile,
        rule_hits: List[RuleHit],
    ) -> float:
        rules_component = min(sum(r.weight for r in rule_hits), 1.0)

        combined = (
            self.weights["anomaly"] * anomaly_result.anomaly_score
            + self.weights["behavior"] * behavior_profile.behavior_risk_score
            + self.weights["rules"] * rules_component
        )
        return round(min(max(combined, 0.0), 1.0) * 100, 2)

    @staticmethod
    def _risk_level_for(score: float) -> RiskLevel:
        for threshold, level in RISK_THRESHOLDS:
            if score >= threshold:
                return level
        return RiskLevel.LOW


if __name__ == "__main__":  # quick manual smoke test
    logging.basicConfig(level=logging.INFO)
    from datetime import timedelta

    engine = FraudScoreEngine()
    engine.fit_baseline([
        {"claim_amount": 1200, "complaints_last_30_days": 1, "hours_since_purchase": 400,
         "hours_since_last_complaint": 2000, "refund_to_purchase_ratio": 0.4}
        for _ in range(20)
    ])

    now = datetime.utcnow()
    history = [
        ComplaintRecord("c1", "cust_9", "Package arrived broken", 900,
                         now - timedelta(hours=4), device_id="dev_X"),
    ]
    new_complaint = ComplaintRecord(
        "c2", "cust_9", "Package arrived broken again, want full refund", 980,
        now, device_id="dev_X",
    )
    assessment = engine.assess(
        complaint=new_complaint,
        purchase_timestamp=now - timedelta(hours=5),
        purchase_amount=1000,
        customer_history=history,
    )
    print(assessment.to_dict())
