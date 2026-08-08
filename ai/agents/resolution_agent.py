"""
resolution_agent.py

Synthesizes Evidence, Policy, and Fraud agent outputs into
an actionable resolution.
"""

from __future__ import annotations

from typing import Optional, Tuple

from .base_agent import AgentResult, BaseAgent, ComplaintContext


FRAUD_DENY_THRESHOLD = 0.8
FRAUD_MANUAL_REVIEW_THRESHOLD = 0.5


class ResolutionAgent(BaseAgent):
    name = "resolution_agent"

    def process(self, context: ComplaintContext) -> AgentResult:

        # ----------------------------------------------------------
        # Fraud
        # ----------------------------------------------------------

        fraud_score = context.fraud_score or 0.0

        # ----------------------------------------------------------
        # Policy
        # ----------------------------------------------------------

        policy_findings = context.policy_findings or {}
        policy_verdict = policy_findings.get("verdict", {}) or {}

        eligibility = policy_verdict.get(
            "eligibility",
            "needs_review",
        )

        # ----------------------------------------------------------
        # Evidence
        # ----------------------------------------------------------

        evidence_findings = context.evidence_findings or {}

        damage_confirmed = bool(
            evidence_findings.get(
                "damage_confirmed",
                False,
            )
        )

        # ----------------------------------------------------------
        # Category
        # ----------------------------------------------------------

        category = self._normalize_category(
            context.category
        )

        # ----------------------------------------------------------
        # Decision
        # ----------------------------------------------------------

        decision, justification, requires_human = self._decide(
            fraud_score=fraud_score,
            eligibility=eligibility,
            damage_confirmed=damage_confirmed,
            category=category,
        )

        # ----------------------------------------------------------
        # Resolution object
        # ----------------------------------------------------------

        resolution = {
            "decision": decision,
            "requires_human_review": requires_human,
            "justification": justification,
            "based_on": {
                "policy_eligibility": eligibility,
                "fraud_score": fraud_score,
                "damage_confirmed": damage_confirmed,
                "category": category,
                "applicable_policy": policy_verdict.get(
                    "applicable_policy"
                ),
            },
        }

        context.resolution = resolution

        # ----------------------------------------------------------
        # Confidence
        # ----------------------------------------------------------

        confidence = self._confidence(
            fraud_score=fraud_score,
            eligibility=eligibility,
            damage_confirmed=damage_confirmed,
            category=category,
        )

        return AgentResult(
            agent_name=self.name,
            success=True,
            data=resolution,
            confidence=confidence,
            reasoning=justification,
        )

    # ==============================================================
    # CATEGORY NORMALIZATION
    # ==============================================================

    def _normalize_category(
        self,
        category: Optional[str],
    ) -> str:

        category = (category or "").lower().strip()

        aliases = {
            # Refund
            "refund": "refund",

            # Damage
            "damaged product": "damaged_product",
            "damaged_product": "damaged_product",
            "damage": "damaged_product",

            # Replacement
            "replacement": "replacement",
            "replace": "replacement",
            "product replacement": "replacement",

            # Delivery
            "delivery": "delivery",
            "delivery delay": "delivery",
            "delivery_delay": "delivery",
            "late delivery": "delivery",

            # Warranty
            "warranty": "warranty",
            "warranty claim": "warranty",
            "warranty_claim": "warranty",

            # Billing
            "billing": "billing",
            "billing issue": "billing",
            "billing_issue": "billing",

            # Other
            "other": "other",
            "general inquiry": "general_inquiry",
            "general_inquiry": "general_inquiry",
        }

        return aliases.get(
            category,
            category,
        )

    # ==============================================================
    # DECISION ENGINE
    # ==============================================================

    def _decide(
        self,
        fraud_score: float,
        eligibility: str,
        damage_confirmed: bool,
        category: Optional[str],
    ) -> Tuple[str, str, bool]:

        # ----------------------------------------------------------
        # 1. HIGH FRAUD
        # ----------------------------------------------------------

        if fraud_score >= FRAUD_DENY_THRESHOLD:

            return (
                "deny_pending_investigation",

                (
                    f"Fraud score {fraud_score:.2f} exceeds "
                    f"the deny threshold "
                    f"({FRAUD_DENY_THRESHOLD}); "
                    "routed to fraud investigation."
                ),

                True,
            )

        # ----------------------------------------------------------
        # 2. EXPLICIT POLICY DENIAL
        # ----------------------------------------------------------

        if eligibility == "not_eligible":

            return (
                "deny",

                (
                    "Policy verdict indicates that this claim "
                    "does not meet eligibility conditions."
                ),

                False,
            )

        # ----------------------------------------------------------
        # 3. DAMAGED PRODUCT WITHOUT EVIDENCE
        # ----------------------------------------------------------

        if (
            category == "damaged_product"
            and not damage_confirmed
        ):

            return (
                "request_additional_evidence",

                (
                    "The product was reported as damaged, "
                    "but the uploaded evidence did not confirm "
                    "the damage."
                ),

                False,
            )

        # ----------------------------------------------------------
        # 4. LOW FRAUD RISK
        #
        # This allows the hackathon demo to continue even when
        # RAG returns needs_review because no policy chunks
        # are currently indexed.
        # ----------------------------------------------------------

        if fraud_score < FRAUD_MANUAL_REVIEW_THRESHOLD:

            action = self._map_category_to_action(
                category=category,
                damage_confirmed=damage_confirmed,
            )

            if action != "manual_review":

                return (
                    action,

                    (
                        f"Low fraud risk "
                        f"(score={fraud_score:.2f}) and "
                        f"category '{category}' identified. "
                        f"AI recommends "
                        f"{action.replace('_', ' ')}."
                    ),

                    False,
                )

        # ----------------------------------------------------------
        # 5. FALLBACK
        # ----------------------------------------------------------

        return (
            "manual_review",

            (
                f"Insufficient confidence to auto-resolve "
                f"(eligibility='{eligibility}', "
                f"fraud_score={fraud_score:.2f}); "
                "escalating to a human agent."
            ),

            True,
        )

    # ==============================================================
    # CATEGORY → ACTION
    # ==============================================================

    def _map_category_to_action(
        self,
        category: Optional[str],
        damage_confirmed: bool,
    ) -> str:

        category = self._normalize_category(category)

        # ----------------------------------------------------------
        # REFUND
        # ----------------------------------------------------------

        if category == "refund":

            return "issue_full_refund"

        # ----------------------------------------------------------
        # DAMAGED PRODUCT
        # ----------------------------------------------------------

        if category == "damaged_product":

            if damage_confirmed:
                return "issue_replacement"

            return "request_additional_evidence"

        # ----------------------------------------------------------
        # REPLACEMENT
        # ----------------------------------------------------------

        if category == "replacement":

            return "issue_replacement"

        # ----------------------------------------------------------
        # DELIVERY
        # ----------------------------------------------------------

        if category == "delivery":

            return "issue_delivery_resolution"

        # ----------------------------------------------------------
        # WARRANTY
        # ----------------------------------------------------------

        if category == "warranty":

            return "schedule_repair"

        # ----------------------------------------------------------
        # BILLING
        # ----------------------------------------------------------

        if category == "billing":

            return "issue_billing_correction"

        # ----------------------------------------------------------
        # OTHER
        # ----------------------------------------------------------

        if category in {
            "other",
            "general_inquiry",
        }:

            return "manual_review"

        # ----------------------------------------------------------
        # UNKNOWN
        # ----------------------------------------------------------

        return "manual_review"

    # ==============================================================
    # CONFIDENCE
    # ==============================================================

    def _confidence(
        self,
        fraud_score: float,
        eligibility: str,
        damage_confirmed: bool,
        category: Optional[str],
    ) -> float:

        # Base confidence from policy

        base = {
            "likely_eligible": 0.80,
            "not_eligible": 0.75,
            "needs_review": 0.65,
        }.get(
            eligibility,
            0.60,
        )

        # Fraud reduces confidence

        base -= 0.30 * fraud_score

        # Evidence increases confidence

        if damage_confirmed:
            base += 0.10

        # Recognized categories increase confidence

        recognized_categories = {
            "refund",
            "damaged_product",
            "replacement",
            "delivery",
            "warranty",
            "billing",
        }

        if category in recognized_categories:
            base += 0.05

        return round(
            max(
                0.05,
                min(base, 0.95),
            ),
            2,
        )