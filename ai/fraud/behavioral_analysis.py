"""
ai/fraud/behavioral_analysis.py

Looks across a customer's complaint history (and, where available,
device/IP metadata) for behavioral fraud signals that a single-complaint
anomaly check would miss: serial filing, duplicate/near-duplicate
complaint text, device sharing across accounts, and rapid escalation
patterns.

Consumed by: ai/fraud/fraud_score.py -> FraudScoreEngine
             ai/agents/fraud_agent.py
             ai/agents/learning_agent.py (pattern feedback loop)
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

logger = logging.getLogger("resolvix.ai.fraud.behavior")

# Kept lightweight (difflib) by default so the module has zero required
# third-party deps; upgrades to a TF-IDF/embedding based similarity
# transparently if scikit-learn is present.
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    _SKLEARN_TEXT_AVAILABLE = True
except ImportError:  # pragma: no cover
    _SKLEARN_TEXT_AVAILABLE = False


@dataclass
class ComplaintRecord:
    """Minimal shape behavioral_analysis needs from a complaint row.
    backend/database/models.py's Complaint ORM model should map to this."""

    complaint_id: str
    customer_id: str
    text: str
    claim_amount: float
    created_at: datetime
    device_id: Optional[str] = None
    ip_address: Optional[str] = None
    status: str = "open"  # open | resolved | rejected | escalated


@dataclass
class BehaviorProfile:
    customer_id: str
    complaint_count_90d: int
    duplicate_text_matches: List[str] = field(default_factory=list)
    shared_device_customers: List[str] = field(default_factory=list)
    rapid_filing_flag: bool = False
    escalation_rate: float = 0.0
    rejection_rate: float = 0.0
    behavior_risk_score: float = 0.0  # 0.0 (normal) - 1.0 (high risk)
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "customer_id": self.customer_id,
            "complaint_count_90d": self.complaint_count_90d,
            "duplicate_text_matches": self.duplicate_text_matches,
            "shared_device_customers": self.shared_device_customers,
            "rapid_filing_flag": self.rapid_filing_flag,
            "escalation_rate": round(self.escalation_rate, 3),
            "rejection_rate": round(self.rejection_rate, 3),
            "behavior_risk_score": round(self.behavior_risk_score, 4),
            "reasons": self.reasons,
        }


class BehaviorAnalyzer:
    def __init__(
        self,
        text_similarity_threshold: float = 0.82,
        rapid_filing_window_hours: int = 6,
        rapid_filing_count: int = 3,
    ):
        self.text_similarity_threshold = text_similarity_threshold
        self.rapid_filing_window_hours = rapid_filing_window_hours
        self.rapid_filing_count = rapid_filing_count

    # ---- public API -----------------------------------------------------

    def analyze_customer(
        self,
        new_complaint: ComplaintRecord,
        customer_history: List[ComplaintRecord],
        all_recent_complaints: Optional[List[ComplaintRecord]] = None,
    ) -> BehaviorProfile:
        """
        new_complaint: the complaint currently being triaged.
        customer_history: prior complaints from the SAME customer.
        all_recent_complaints: recent complaints across ALL customers,
            used for cross-account device/IP sharing checks. Optional —
            pass None to skip that check (e.g. for a lightweight demo).
        """
        reasons: List[str] = []
        window_90d = new_complaint.created_at - timedelta(days=90)
        recent = [c for c in customer_history if c.created_at >= window_90d]

        duplicate_matches = self._find_duplicate_text(new_complaint, customer_history)
        if duplicate_matches:
            reasons.append(
                f"Near-duplicate complaint text vs {len(duplicate_matches)} prior complaint(s)"
            )

        shared_device = self._find_shared_devices(new_complaint, all_recent_complaints or [])
        if shared_device:
            reasons.append(f"Device/IP shared with {len(shared_device)} other account(s)")

        rapid_filing = self._is_rapid_filing(new_complaint, customer_history)
        if rapid_filing:
            reasons.append(
                f">= {self.rapid_filing_count} complaints within "
                f"{self.rapid_filing_window_hours}h window"
            )

        escalation_rate = self._rate(recent, lambda c: c.status == "escalated")
        rejection_rate = self._rate(recent, lambda c: c.status == "rejected")
        if rejection_rate >= 0.5 and len(recent) >= 3:
            reasons.append(f"High historical rejection rate ({rejection_rate:.0%})")

        risk_score = self._compute_risk_score(
            duplicate_matches=duplicate_matches,
            shared_device=shared_device,
            rapid_filing=rapid_filing,
            escalation_rate=escalation_rate,
            rejection_rate=rejection_rate,
            complaint_count_90d=len(recent),
        )

        return BehaviorProfile(
            customer_id=new_complaint.customer_id,
            complaint_count_90d=len(recent),
            duplicate_text_matches=[c.complaint_id for c in duplicate_matches],
            shared_device_customers=[c.customer_id for c in shared_device],
            rapid_filing_flag=rapid_filing,
            escalation_rate=escalation_rate,
            rejection_rate=rejection_rate,
            behavior_risk_score=risk_score,
            reasons=reasons,
        )

    # ---- internal checks --------------------------------------------------

    def _find_duplicate_text(
        self, new_complaint: ComplaintRecord, history: List[ComplaintRecord]
    ) -> List[ComplaintRecord]:
        if not history:
            return []

        if _SKLEARN_TEXT_AVAILABLE and len(history) >= 3:
            corpus = [new_complaint.text] + [c.text for c in history]
            try:
                tfidf = TfidfVectorizer(stop_words="english").fit_transform(corpus)
                sims = cosine_similarity(tfidf[0:1], tfidf[1:])[0]
                return [
                    history[i] for i, s in enumerate(sims)
                    if s >= self.text_similarity_threshold
                ]
            except ValueError:
                pass  # e.g. empty vocabulary — fall through to difflib

        matches = []
        for record in history:
            ratio = SequenceMatcher(None, new_complaint.text.lower(), record.text.lower()).ratio()
            if ratio >= self.text_similarity_threshold:
                matches.append(record)
        return matches

    def _find_shared_devices(
        self, new_complaint: ComplaintRecord, all_recent: List[ComplaintRecord]
    ) -> List[ComplaintRecord]:
        if not (new_complaint.device_id or new_complaint.ip_address):
            return []

        matches = []
        for record in all_recent:
            if record.customer_id == new_complaint.customer_id:
                continue
            same_device = new_complaint.device_id and record.device_id == new_complaint.device_id
            same_ip = new_complaint.ip_address and record.ip_address == new_complaint.ip_address
            if same_device or same_ip:
                matches.append(record)
        return matches

    def _is_rapid_filing(
        self, new_complaint: ComplaintRecord, history: List[ComplaintRecord]
    ) -> bool:
        window_start = new_complaint.created_at - timedelta(hours=self.rapid_filing_window_hours)
        count = sum(1 for c in history if c.created_at >= window_start) + 1  # include new one
        return count >= self.rapid_filing_count

    @staticmethod
    def _rate(records: List[ComplaintRecord], predicate) -> float:
        if not records:
            return 0.0
        return sum(1 for r in records if predicate(r)) / len(records)

    @staticmethod
    def _compute_risk_score(
        duplicate_matches: List[ComplaintRecord],
        shared_device: List[ComplaintRecord],
        rapid_filing: bool,
        escalation_rate: float,
        rejection_rate: float,
        complaint_count_90d: int,
    ) -> float:
        score = 0.0
        score += min(len(duplicate_matches) * 0.25, 0.5)
        score += min(len(shared_device) * 0.3, 0.6)
        score += 0.25 if rapid_filing else 0.0
        score += min(rejection_rate * 0.3, 0.3)
        score += min(max(complaint_count_90d - 3, 0) * 0.05, 0.2)
        return min(score, 1.0)


if __name__ == "__main__":  # quick manual smoke test
    logging.basicConfig(level=logging.INFO)
    now = datetime.utcnow()
    history = [
        ComplaintRecord("c1", "cust_1", "My order arrived damaged, box was crushed", 500,
                         now - timedelta(hours=5), device_id="dev_A"),
        ComplaintRecord("c2", "cust_1", "Item never arrived, no update", 700,
                         now - timedelta(hours=3), device_id="dev_A"),
    ]
    new = ComplaintRecord("c3", "cust_1", "My order arrived damaged, the box was crushed badly", 650,
                           now, device_id="dev_A")
    profile = BehaviorAnalyzer().analyze_customer(new, history)
    print(profile.to_dict())
