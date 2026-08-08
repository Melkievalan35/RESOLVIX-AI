"""
evidence_agent.py
Processes attachments submitted with a complaint: product photos and
invoices. Delegates actual pixel/text extraction to the ai/vision and
ai/ocr modules and aggregates the findings into a single evidence report.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .base_agent import AgentResult, BaseAgent, ComplaintContext

# These come from the sibling modules in ai/vision and ai/ocr.
# Imported lazily / defensively so this agent still runs (in degraded mode)
# if those modules aren't wired up yet in a given environment.
try:
    from ai.vision.image_analyzer import analyze_image
    from ai.vision.damage_detector import detect_damage
    from ai.ocr.invoice_reader import read_invoice

    print("✅ Vision modules loaded")

except Exception as e:
    print("❌ Import Error:", e)

    analyze_image = None
    detect_damage = None
    read_invoice = None


IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
DOCUMENT_EXTENSIONS = (".pdf",)


class EvidenceAgent(BaseAgent):
    name = "evidence_agent"

    def process(self, context: ComplaintContext) -> AgentResult:
        if not context.attachments:
            return AgentResult(
                agent_name=self.name,
                success=True,
                data={"has_evidence": False},
                confidence=0.5,
                reasoning="No attachments were provided with this complaint.",
            )

        image_findings: List[Dict[str, Any]] = []
        invoice_findings: List[Dict[str, Any]] = []
        errors: List[str] = []

        for path in context.attachments:
            lower = path.lower()
            try:
                if lower.endswith(IMAGE_EXTENSIONS):
                    image_findings.append(self._process_image(path))
                elif lower.endswith(DOCUMENT_EXTENSIONS):
                    invoice_findings.append(self._process_invoice(path))
                else:
                    errors.append(f"Unsupported attachment type: {path}")
            except Exception as exc:
                errors.append(f"{path}: {exc}")

        damage_confirmed = any(
            img.get("damage_detected", False) for img in image_findings
        )

        avg_confidence = self._average_confidence(
            image_findings + invoice_findings
        )

        context.evidence_findings = {
            "images": image_findings,
            "invoices": invoice_findings,
            "damage_confirmed": damage_confirmed,
            "errors": errors,
        }

        return AgentResult(
            agent_name=self.name,
            success=len(errors) < len(context.attachments),
            data=context.evidence_findings,
            confidence=avg_confidence,
            reasoning=(
                f"Processed {len(image_findings)} image(s) and "
                f"{len(invoice_findings)} invoice(s). "
                f"Damage confirmed: {damage_confirmed}."
            ),
            error="; ".join(errors) if errors else None,
        )

    def _process_image(self, path: str) -> Dict[str, Any]:
        if analyze_image is None or detect_damage is None:
            return {
                "path": path,
                "damage_detected": None,
                "note": "vision module unavailable",
            }

        classification = analyze_image(path)
        damage = detect_damage(path)

        return {
            "path": path,
            "classification": classification,
            "damage_detected": damage["damage_detected"],
            "severity": damage["severity"],
            "damage_score": damage["damage_score"],
            "regions": damage["regions"],
            "notes": damage["notes"],
        }

    def _process_invoice(self, path: str) -> Dict[str, Any]:
        if read_invoice is None:
            return {
                "path": path,
                "note": "OCR module unavailable",
            }

        extracted = read_invoice(path)
        return {
            "path": path,
            **extracted,
        }

    def _average_confidence(
        self,
        findings: List[Dict[str, Any]],
    ) -> float:
        scores = []

        for f in findings:
            if "damage_score" in f:
                scores.append(f["damage_score"])

        if not scores:
            return 0.5

        return round(sum(scores) / len(scores), 2)

    def _process_invoice(self, path: str) -> Dict[str, Any]:
        if read_invoice is None:
            return {"path": path, "note": "OCR module unavailable"}
        extracted = read_invoice(path)
        return {"path": path, **extracted}

    def _average_confidence(self, findings: List[Dict[str, Any]]) -> float:
        scores = [f.get("damage_confidence", 0.6) for f in findings if isinstance(f, dict)]
        return round(sum(scores) / len(scores), 2) if scores else 0.5
