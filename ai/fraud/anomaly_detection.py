"""
ai/fraud/anomaly_detection.py

Detects statistically anomalous complaints (e.g. unusually high claim
amounts, abnormal filing frequency, suspicious timing) using an
IsolationForest when scikit-learn is available, with an automatic
z-score fallback so the module never hard-fails in a constrained
hackathon environment.

Consumed by: ai/fraud/fraud_score.py -> FraudScoreEngine
             ai/agents/fraud_agent.py
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("resolvix.ai.fraud.anomaly")

try:
    from sklearn.ensemble import IsolationForest
    import numpy as np
    _SKLEARN_AVAILABLE = True
except ImportError:  # pragma: no cover - environment without sklearn
    _SKLEARN_AVAILABLE = False
    logger.warning(
        "scikit-learn not available — AnomalyDetector will use the "
        "z-score fallback instead of IsolationForest."
    )

# Feature keys expected in the dict passed to AnomalyDetector.detect().
# Kept as a constant so complaint_service.py / fraud_agent.py can build
# a compliant payload without guessing key names.
FEATURE_KEYS = [
    "claim_amount",
    "complaints_last_30_days",
    "hours_since_purchase",
    "hours_since_last_complaint",
    "refund_to_purchase_ratio",
]


@dataclass
class AnomalyResult:
    is_anomaly: bool
    anomaly_score: float  # normalized 0.0 (normal) - 1.0 (highly anomalous)
    method: str
    reasons: List[str] = field(default_factory=list)
    raw_features: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_anomaly": self.is_anomaly,
            "anomaly_score": round(self.anomaly_score, 4),
            "method": self.method,
            "reasons": self.reasons,
            "raw_features": self.raw_features,
        }


class AnomalyDetector:
    """
    Wraps an IsolationForest (preferred) or a per-feature z-score
    fallback behind a single stable interface: fit() then detect().
    """

    def __init__(self, contamination: float = 0.08, z_threshold: float = 2.5):
        self.contamination = contamination
        self.z_threshold = z_threshold
        self._model: Optional["IsolationForest"] = None
        self._feature_stats: Dict[str, Dict[str, float]] = {}
        self._fitted = False

    def fit(self, historical_complaints: List[Dict[str, float]]) -> "AnomalyDetector":
        """
        historical_complaints: list of feature dicts (see FEATURE_KEYS).
        Safe to call with an empty/small list — falls back to permissive
        defaults so a cold-started demo doesn't crash mid-hackathon.
        """
        if not historical_complaints:
            logger.info("No historical data supplied; using default baseline stats.")
            self._feature_stats = {
                k: {"mean": 0.0, "stdev": 1.0} for k in FEATURE_KEYS
            }
            self._fitted = True
            return self

        matrix = [[row.get(k, 0.0) for k in FEATURE_KEYS] for row in historical_complaints]

        # Always compute z-score stats — used as fallback or as a sanity
        # cross-check alongside IsolationForest.
        for idx, key in enumerate(FEATURE_KEYS):
            column = [row[idx] for row in matrix]
            mean = statistics.fmean(column)
            stdev = statistics.pstdev(column) or 1.0
            self._feature_stats[key] = {"mean": mean, "stdev": stdev}

        if _SKLEARN_AVAILABLE and len(historical_complaints) >= 10:
            self._model = IsolationForest(
                contamination=self.contamination, random_state=42
            )
            self._model.fit(np.array(matrix))
            logger.info("IsolationForest fitted on %d historical complaints.", len(matrix))
        else:
            self._model = None

        self._fitted = True
        return self

    def detect(self, features: Dict[str, float]) -> AnomalyResult:
        if not self._fitted:
            self.fit([])  # lazy default fit so callers can't forget

        vector = [features.get(k, 0.0) for k in FEATURE_KEYS]

        if self._model is not None:
            score = self._model.decision_function([vector])[0]  # higher = more normal
            prediction = self._model.predict([vector])[0]  # -1 anomaly, 1 normal
            # Normalize decision_function (~[-0.5, 0.5]) into 0-1 anomaly score.
            forest_score = min(max((0.5 - score) / 1.0, 0.0), 1.0)

            # IsolationForest degenerates on small/low-variance training
            # sets (common early in a hackathon demo before real history
            # accumulates), so cross-check against the z-score signal and
            # take whichever is more confident rather than trusting the
            # forest blindly.
            z_is_anomaly, z_score, reasons = self._zscore_fallback(features)
            anomaly_score = max(forest_score, z_score)
            is_anomaly = (prediction == -1) or z_is_anomaly
            method = "isolation_forest+zscore_crosscheck"
        else:
            is_anomaly, anomaly_score, reasons = self._zscore_fallback(features)
            method = "zscore_fallback"

        return AnomalyResult(
            is_anomaly=is_anomaly,
            anomaly_score=anomaly_score,
            method=method,
            reasons=reasons,
            raw_features={k: features.get(k, 0.0) for k in FEATURE_KEYS},
        )

    def _zscore_fallback(self, features: Dict[str, float]):
        flags = []
        z_scores = []
        for key in FEATURE_KEYS:
            stats = self._feature_stats.get(key, {"mean": 0.0, "stdev": 1.0})
            value = features.get(key, 0.0)
            z = abs(value - stats["mean"]) / (stats["stdev"] or 1.0)
            z_scores.append(z)
            if z >= self.z_threshold:
                flags.append(f"{key}={value} is {z:.1f} std devs from norm")

        max_z = max(z_scores) if z_scores else 0.0
        anomaly_score = min(max_z / (self.z_threshold * 2), 1.0)
        is_anomaly = len(flags) > 0
        return is_anomaly, anomaly_score, flags


def build_features_from_complaint(
    claim_amount: float,
    purchase_timestamp: datetime,
    complaint_timestamp: datetime,
    prior_complaints_last_30_days: int,
    last_complaint_timestamp: Optional[datetime],
    purchase_amount: float,
) -> Dict[str, float]:
    """
    Convenience adapter so backend/services/complaint_service.py can pass
    raw complaint fields instead of pre-engineering features itself.
    """
    hours_since_purchase = max(
        (complaint_timestamp - purchase_timestamp).total_seconds() / 3600.0, 0.0
    )
    hours_since_last_complaint = (
        max((complaint_timestamp - last_complaint_timestamp).total_seconds() / 3600.0, 0.0)
        if last_complaint_timestamp
        else 24 * 365.0  # treat "no prior complaint" as a long gap
    )
    refund_ratio = claim_amount / purchase_amount if purchase_amount else 0.0

    return {
        "claim_amount": claim_amount,
        "complaints_last_30_days": float(prior_complaints_last_30_days),
        "hours_since_purchase": hours_since_purchase,
        "hours_since_last_complaint": hours_since_last_complaint,
        "refund_to_purchase_ratio": refund_ratio,
    }


if __name__ == "__main__":  # quick manual smoke test
    logging.basicConfig(level=logging.INFO)
    detector = AnomalyDetector().fit([
        {"claim_amount": 1200, "complaints_last_30_days": 1, "hours_since_purchase": 400,
         "hours_since_last_complaint": 2000, "refund_to_purchase_ratio": 0.4}
        for _ in range(20)
    ])
    suspicious = {
        "claim_amount": 9800,
        "complaints_last_30_days": 6,
        "hours_since_purchase": 1.0,
        "hours_since_last_complaint": 0.5,
        "refund_to_purchase_ratio": 0.98,
    }
    print(detector.detect(suspicious).to_dict())
