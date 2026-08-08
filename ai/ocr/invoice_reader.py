"""
invoice_reader.py
------------------
Structured invoice / receipt parsing for the AI complaint-resolution
pipeline. Where text_extractor.py gives you raw OCR text, this module
turns that text into structured fields (invoice number, date, vendor,
line items, total) so the policy_agent / resolution_agent can verify
refund eligibility, warranty windows, and claimed amounts automatically.

Pipeline:
    1. Reuse TextExtractor for OCR (composition, not duplication).
    2. Parse structured fields with targeted regex/heuristics:
       invoice number, date, total amount, vendor/merchant name,
       line items (description + price).
    3. Cross-check: does the claimed refund amount actually appear on
       the invoice? Is the purchase date within policy window?

Dependencies:
    pip install pytesseract opencv-python-headless pillow numpy
    (same system dependency as text_extractor.py: tesseract-ocr)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

from .text_extractor import TextExtractor, OCRResult  # sibling module in ai/ocr/

logger = logging.getLogger("resolvix.ai.ocr.invoice_reader")


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #

@dataclass
class LineItem:
    description: str
    amount: float


@dataclass
class InvoiceData:
    invoice_number: Optional[str] = None
    vendor_name: Optional[str] = None
    purchase_date: Optional[str] = None       # ISO format if parsed successfully
    purchase_date_raw: Optional[str] = None   # original matched string
    total_amount: Optional[float] = None
    currency: Optional[str] = None
    line_items: List[LineItem] = field(default_factory=list)
    ocr_confidence: float = 0.0
    is_reliable: bool = True
    warnings: List[str] = field(default_factory=list)


@dataclass
class VerificationResult:
    amount_matches: Optional[bool]
    within_policy_window: Optional[bool]
    days_since_purchase: Optional[int]
    details: List[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Patterns
# --------------------------------------------------------------------------- #

INVOICE_NUMBER_PATTERNS = [
    re.compile(r"(?:invoice|inv|bill)[\s#:.]*([A-Z0-9\-/]{4,20})", re.IGNORECASE),
    re.compile(r"(?:order|ord)[\s#:.]*([A-Z0-9\-/]{4,20})", re.IGNORECASE),
]

DATE_PATTERNS = [
    (re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b"), "%d-%m-%Y"),
    (re.compile(r"\b(\d{4})[/-](\d{1,2})[/-](\d{1,2})\b"), "%Y-%m-%d"),
    (re.compile(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})\b"), "%d-%b-%Y"),
]

TOTAL_PATTERNS = [
    re.compile(r"(?:grand\s*total|total\s*amount|total)[\s:]*(?:₹|\$|Rs\.?|INR|USD)?\s?([\d,]+\.\d{2})", re.IGNORECASE),
    re.compile(r"(?:grand\s*total|total\s*amount|total)[\s:]*(?:₹|\$|Rs\.?|INR|USD)?\s?([\d,]+)", re.IGNORECASE),
]

CURRENCY_PATTERNS = {
    "INR": re.compile(r"₹|Rs\.?|INR"),
    "USD": re.compile(r"\$|USD"),
    "EUR": re.compile(r"€|EUR"),
}

LINE_ITEM_PATTERN = re.compile(
    r"([A-Za-z][A-Za-z0-9 &\-]{2,40})\s+(?:₹|\$|Rs\.?)?\s?([\d,]+\.\d{2})"
)


class InvoiceReaderConfig:
    DEFAULT_REFUND_WINDOW_DAYS = 30
    DEFAULT_WARRANTY_WINDOW_DAYS = 365
    AMOUNT_MATCH_TOLERANCE = 0.02  # 2% tolerance for OCR rounding errors


# --------------------------------------------------------------------------- #
# Core class
# --------------------------------------------------------------------------- #

class InvoiceReader:
    """
    Parses structured fields out of an invoice/receipt image and can
    verify a claimed refund amount / policy window against it.
    """

    def __init__(self, config: Optional[InvoiceReaderConfig] = None):
        self.config = config or InvoiceReaderConfig()
        self.text_extractor = TextExtractor()

    # ---------------------------- field extraction ---------------------------- #

    def _extract_invoice_number(self, text: str) -> Optional[str]:
        for pattern in INVOICE_NUMBER_PATTERNS:
            match = pattern.search(text)
            if match:
                return match.group(1).strip()
        return None

    def _extract_date(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        for pattern, fmt in DATE_PATTERNS:
            match = pattern.search(text)
            if not match:
                continue
            raw = match.group(0)
            try:
                if fmt == "%d-%b-%Y":
                    day, month_name, year = match.groups()
                    parsed = datetime.strptime(f"{day}-{month_name}-{year}", "%d-%b-%Y")
                elif fmt == "%Y-%m-%d":
                    year, month, day = match.groups()
                    parsed = datetime(int(year), int(month), int(day))
                else:  # %d-%m-%Y
                    day, month, year = match.groups()
                    parsed = datetime(int(year), int(month), int(day))
                return parsed.date().isoformat(), raw
            except (ValueError, TypeError):
                continue  # try next pattern
        return None, None

    def _extract_total(self, text: str) -> Optional[float]:
        for pattern in TOTAL_PATTERNS:
            match = pattern.search(text)
            if match:
                amount_str = match.group(1).replace(",", "")
                try:
                    return float(amount_str)
                except ValueError:
                    continue
        return None

    def _extract_currency(self, text: str) -> Optional[str]:
        for code, pattern in CURRENCY_PATTERNS.items():
            if pattern.search(text):
                return code
        return None

    def _extract_vendor(self, text: str) -> Optional[str]:
        """
        Heuristic: vendor name is often the first non-empty line of a
        receipt, before any 'invoice'/'date'/'total' keywords appear.
        """
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        for line in lines[:3]:
            if len(line) > 2 and not re.search(r"\d{3,}", line):
                return line
        return None

    def _extract_line_items(self, text: str) -> List[LineItem]:
        items = []
        for match in LINE_ITEM_PATTERN.finditer(text):
            desc, amount_str = match.groups()
            try:
                amount = float(amount_str.replace(",", ""))
            except ValueError:
                continue
            items.append(LineItem(description=desc.strip(), amount=amount))
        return items[:25]  # cap to avoid noise explosions on messy OCR

    # ---------------------------- public API ---------------------------- #

    def parse(self, image: np.ndarray) -> InvoiceData:
        ocr_result: OCRResult = self.text_extractor.extract(image)
        text = ocr_result.cleaned_text

        invoice_number = self._extract_invoice_number(text)
        purchase_date, purchase_date_raw = self._extract_date(text)
        total_amount = self._extract_total(text)
        currency = self._extract_currency(text)
        vendor_name = self._extract_vendor(text)
        line_items = self._extract_line_items(text)

        warnings = list(ocr_result.notes)
        if invoice_number is None:
            warnings.append("Could not locate an invoice/order number.")
        if purchase_date is None:
            warnings.append("Could not locate a valid purchase date.")
        if total_amount is None:
            warnings.append("Could not locate a total amount.")

        return InvoiceData(
            invoice_number=invoice_number,
            vendor_name=vendor_name,
            purchase_date=purchase_date,
            purchase_date_raw=purchase_date_raw,
            total_amount=total_amount,
            currency=currency,
            line_items=line_items,
            ocr_confidence=ocr_result.avg_confidence,
            is_reliable=ocr_result.is_reliable,
            warnings=warnings,
        )

    def parse_from_path(self, path: str) -> InvoiceData:
        image = cv2.imread(path, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"Could not decode image at: {path}")
        return self.parse(image)

    # ---------------------------- verification ---------------------------- #

    def verify_claim(
        self,
        invoice: InvoiceData,
        claimed_amount: Optional[float] = None,
        policy_window_days: Optional[int] = None,
        reference_date: Optional[datetime] = None,
    ) -> VerificationResult:
        """
        Cross-checks a customer's complaint claim against the parsed
        invoice: does the claimed refund amount match, and is the
        purchase within the applicable policy window (refund/warranty)?
        """
        reference_date = reference_date or datetime.utcnow()
        policy_window_days = policy_window_days or self.config.DEFAULT_REFUND_WINDOW_DAYS

        details: List[str] = []

        # Amount check
        amount_matches: Optional[bool] = None
        if claimed_amount is not None and invoice.total_amount is not None:
            tolerance = invoice.total_amount * self.config.AMOUNT_MATCH_TOLERANCE
            amount_matches = abs(claimed_amount - invoice.total_amount) <= tolerance
            details.append(
                f"Claimed amount {claimed_amount} vs invoice total {invoice.total_amount}: "
                f"{'match' if amount_matches else 'mismatch'}"
            )
        else:
            details.append("Insufficient data to verify claimed amount.")

        # Policy window check
        within_window: Optional[bool] = None
        days_since: Optional[int] = None
        if invoice.purchase_date is not None:
            purchase_dt = datetime.fromisoformat(invoice.purchase_date)
            days_since = (reference_date - purchase_dt).days
            within_window = 0 <= days_since <= policy_window_days
            details.append(
                f"Purchase was {days_since} day(s) ago; policy window is "
                f"{policy_window_days} day(s): "
                f"{'within window' if within_window else 'outside window'}"
            )
        else:
            details.append("Insufficient data to verify policy window (no purchase date).")

        return VerificationResult(
            amount_matches=amount_matches,
            within_policy_window=within_window,
            days_since_purchase=days_since,
            details=details,
        )


# --------------------------------------------------------------------------- #
# Convenience function for pipeline integration
# --------------------------------------------------------------------------- #

def read_invoice(
    path: str,
    claimed_amount: Optional[float] = None,
    policy_window_days: Optional[int] = None,
) -> Dict[str, Any]:
    reader = InvoiceReader()
    invoice = reader.parse_from_path(path)
    verification = reader.verify_claim(
        invoice, claimed_amount=claimed_amount, policy_window_days=policy_window_days
    )

    return {
        "invoice": {
            "invoice_number": invoice.invoice_number,
            "vendor_name": invoice.vendor_name,
            "purchase_date": invoice.purchase_date,
            "total_amount": invoice.total_amount,
            "currency": invoice.currency,
            "line_items": [li.__dict__ for li in invoice.line_items],
            "ocr_confidence": invoice.ocr_confidence,
            "is_reliable": invoice.is_reliable,
            "warnings": invoice.warnings,
        },
        "verification": {
            "amount_matches": verification.amount_matches,
            "within_policy_window": verification.within_policy_window,
            "days_since_purchase": verification.days_since_purchase,
            "details": verification.details,
        },
    }


if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python invoice_reader.py <image_path> [claimed_amount] [policy_window_days]")
        sys.exit(1)

    img_path = sys.argv[1]
    claimed = float(sys.argv[2]) if len(sys.argv) > 2 else None
    window = int(sys.argv[3]) if len(sys.argv) > 3 else None

    print(json.dumps(read_invoice(img_path, claimed, window), indent=2, default=str))
