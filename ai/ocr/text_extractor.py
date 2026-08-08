"""
text_extractor.py
------------------
General-purpose OCR utility for the AI complaint-resolution pipeline.
Used for screenshots, ID/proof-of-purchase documents, and any evidence
image where we need raw text out (as opposed to structured invoice
fields — see invoice_reader.py for that).

Pipeline:
    1. Preprocess image (grayscale, deskew, denoise, threshold) to
       maximize OCR accuracy.
    2. Run OCR (Tesseract via pytesseract).
    3. Post-process: clean whitespace, compute a confidence score,
       optionally extract common patterns (emails, phone numbers,
       order IDs, dates) via regex so downstream agents can grab
       structured hints without a full parser.

Dependencies:
    pip install pytesseract opencv-python-headless pillow numpy
    # System dependency (OCR engine itself):
    #   Ubuntu/Debian: sudo apt-get install tesseract-ocr
    #   macOS:          brew install tesseract
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

try:
    import pytesseract
except ImportError:  # pragma: no cover
    pytesseract = None

logger = logging.getLogger("resolvix.ai.ocr.text_extractor")


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #

@dataclass
class OCRWord:
    text: str
    confidence: float
    bbox: List[int]  # [x, y, w, h]


@dataclass
class OCRResult:
    raw_text: str
    cleaned_text: str
    avg_confidence: float
    words: List[OCRWord] = field(default_factory=list)
    entities: Dict[str, List[str]] = field(default_factory=dict)
    is_reliable: bool = True
    notes: List[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

class TextExtractorConfig:
    MIN_CONFIDENCE = 40.0          # tesseract word-level confidence (0-100)
    MIN_AVG_CONFIDENCE = 55.0      # below this, flag result as unreliable
    TESSERACT_LANG = "eng"
    TESSERACT_CONFIG = "--oem 3 --psm 6"  # assume a uniform block of text
    ADAPTIVE_THRESH_BLOCK_SIZE = 31
    ADAPTIVE_THRESH_C = 15


# Common patterns useful for a complaint-resolution context
ENTITY_PATTERNS = {
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "phone": re.compile(r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}"),
    "order_id": re.compile(r"\b(?:ORD|ORDER|REF|TXN)[-#:\s]?[A-Z0-9]{5,15}\b", re.IGNORECASE),
    "date": re.compile(
        r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\b"
    ),
    "amount": re.compile(r"(?:₹|\$|USD|INR|Rs\.?)\s?[\d,]+\.?\d{0,2}"),
}


# --------------------------------------------------------------------------- #
# Core class
# --------------------------------------------------------------------------- #

class TextExtractor:
    """
    Runs OCR on complaint-evidence images (screenshots, ID docs,
    general text-bearing photos) and extracts useful entities.
    """

    def __init__(self, config: Optional[TextExtractorConfig] = None):
        if cv2 is None:
            raise ImportError("TextExtractor requires opencv-python-headless.")
        if pytesseract is None:
            raise ImportError(
                "TextExtractor requires pytesseract (and the tesseract-ocr "
                "system binary). pip install pytesseract"
            )
        self.config = config or TextExtractorConfig()

    # ---------------------------- preprocessing ---------------------------- #

    def _deskew(self, gray: np.ndarray) -> np.ndarray:
        """Corrects small rotation using minAreaRect on thresholded text pixels."""
        coords = np.column_stack(np.where(gray < 250))
        if coords.shape[0] < 20:
            return gray  # not enough signal to deskew reliably

        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle

        if abs(angle) < 0.5:  # not worth rotating
            return gray

        (h, w) = gray.shape[:2]
        center = (w // 2, h // 2)
        matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        return cv2.warpAffine(
            gray, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
        )

    def _preprocess(self, image: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray = cv2.fastNlMeansDenoising(gray, h=10)
        gray = self._deskew(gray)
        thresh = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            self.config.ADAPTIVE_THRESH_BLOCK_SIZE,
            self.config.ADAPTIVE_THRESH_C,
        )
        return thresh

    # ---------------------------- OCR ---------------------------- #

    def _run_ocr(self, processed: np.ndarray) -> OCRResult:
        data = pytesseract.image_to_data(
            processed,
            lang=self.config.TESSERACT_LANG,
            config=self.config.TESSERACT_CONFIG,
            output_type=pytesseract.Output.DICT,
        )

        words: List[OCRWord] = []
        confidences: List[float] = []

        n = len(data["text"])
        for i in range(n):
            text = data["text"][i].strip()
            conf = float(data["conf"][i]) if data["conf"][i] not in ("-1", -1) else -1.0
            if not text or conf < 0:
                continue
            if conf < self.config.MIN_CONFIDENCE:
                continue  # drop noisy low-confidence tokens

            words.append(
                OCRWord(
                    text=text,
                    confidence=conf,
                    bbox=[data["left"][i], data["top"][i], data["width"][i], data["height"][i]],
                )
            )
            confidences.append(conf)

        raw_text = " ".join(w.text for w in words)
        cleaned_text = self._clean_text(raw_text)
        avg_conf = round(sum(confidences) / len(confidences), 2) if confidences else 0.0

        return OCRResult(
            raw_text=raw_text,
            cleaned_text=cleaned_text,
            avg_confidence=avg_conf,
            words=words,
            is_reliable=avg_conf >= self.config.MIN_AVG_CONFIDENCE,
        )

    # ---------------------------- postprocessing ---------------------------- #

    def _clean_text(self, text: str) -> str:
        text = re.sub(r"\s+", " ", text)
        text = text.strip()
        return text

    def _extract_entities(self, text: str) -> Dict[str, List[str]]:
        entities: Dict[str, List[str]] = {}
        for name, pattern in ENTITY_PATTERNS.items():
            matches = list(dict.fromkeys(pattern.findall(text)))  # dedupe, keep order
            if matches:
                entities[name] = matches
        return entities

    # ---------------------------- public API ---------------------------- #

    def extract(self, image: np.ndarray) -> OCRResult:
        processed = self._preprocess(image)
        result = self._run_ocr(processed)
        result.entities = self._extract_entities(result.cleaned_text)

        if not result.is_reliable:
            result.notes.append(
                f"Low OCR confidence ({result.avg_confidence}); consider requesting "
                "a clearer photo from the customer."
            )
        if not result.raw_text:
            result.notes.append("No text detected in image.")

        return result

    def extract_from_path(self, path: str) -> OCRResult:
        image = cv2.imread(path, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"Could not decode image at: {path}")
        return self.extract(image)


# --------------------------------------------------------------------------- #
# Convenience function for pipeline integration
# --------------------------------------------------------------------------- #

def extract_text(path: str) -> Dict[str, Any]:
    extractor = TextExtractor()
    result = extractor.extract_from_path(path)
    return {
        "raw_text": result.raw_text,
        "cleaned_text": result.cleaned_text,
        "avg_confidence": result.avg_confidence,
        "is_reliable": result.is_reliable,
        "entities": result.entities,
        "notes": result.notes,
        "word_count": len(result.words),
    }


if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) != 2:
        print("Usage: python text_extractor.py <image_path>")
        sys.exit(1)

    print(json.dumps(extract_text(sys.argv[1]), indent=2, default=str))
