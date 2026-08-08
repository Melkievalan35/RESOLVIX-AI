"""
image_classifier.py
--------------------
Classifies an uploaded complaint image into a category so the
orchestrator agent can route it to the right downstream handler
(damage_detector, ocr/invoice_reader, or general evidence review).

Categories:
    - product_damage   : physical product photo, possibly damaged
    - invoice_receipt   : bill/invoice/receipt document photo
    - packaging          : box/packaging photo
    - screenshot          : app/website screenshot (e.g. order status, chat)
    - id_document          : ID/proof-of-purchase style document
    - other                  : unclassified

Two modes:
    1. Heuristic mode (default): uses simple, fast signals (aspect ratio,
       text density via edge/contour statistics, color histogram) to
       make a reasonable guess without needing a trained model.
    2. Model mode: plug in a trained classifier (e.g. a fine-tuned
       torchvision ResNet/EfficientNet) via `ImageClassifier(model=...)`.

Dependencies:
    pip install opencv-python-headless numpy
    # optional, for model mode:
    pip install torch torchvision
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Tuple

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

logger = logging.getLogger("resolvix.ai.vision.image_classifier")

CATEGORIES = [
    "product_damage",
    "invoice_receipt",
    "packaging",
    "screenshot",
    "id_document",
    "other",
]


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #

@dataclass
class ClassificationResult:
    category: str
    confidence: float
    scores: Dict[str, float] = field(default_factory=dict)
    routed_to: str = ""


class ClassifierModel(Protocol):
    """Interface any pluggable deep-learning classifier must satisfy."""

    def predict_proba(self, image: np.ndarray) -> Dict[str, float]:
        ...


# Maps each category to the downstream AI agent/module that should handle it
ROUTING_TABLE = {
    "product_damage": "ai.vision.damage_detector",
    "invoice_receipt": "ai.ocr.invoice_reader",
    "packaging": "ai.vision.damage_detector",
    "screenshot": "ai.ocr.text_extractor",
    "id_document": "ai.ocr.text_extractor",
    "other": "ai.agents.evidence_agent",
}


# --------------------------------------------------------------------------- #
# Core class
# --------------------------------------------------------------------------- #

class ImageClassifier:
    """
    Classifies a complaint-evidence image into one of CATEGORIES.
    Falls back to lightweight heuristics unless a trained `model` is
    supplied.
    """

    def __init__(self, model: Optional[ClassifierModel] = None):
        if cv2 is None:
            raise ImportError("ImageClassifier requires opencv-python-headless.")
        self.model = model

    # ---------------------------- heuristic signals ---------------------------- #

    def _text_density(self, gray: np.ndarray) -> float:
        """
        Rough proxy for 'how much text-like structure is in this image'.
        Documents/screenshots/invoices have dense small edges; product
        photos have sparser, larger structures.
        """
        edges = cv2.Canny(gray, 50, 150)
        # Count small connected components, a proxy for text glyphs/lines
        contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        small_components = sum(1 for c in contours if 5 < cv2.contourArea(c) < 200)
        return small_components / max(1, gray.size / 10000)

    def _aspect_ratio(self, image: np.ndarray) -> float:
        h, w = image.shape[:2]
        return w / h if h else 1.0

    def _color_variance(self, image: np.ndarray) -> float:
        """Documents/screenshots tend to be low color-variance (mostly white/gray)."""
        return float(np.std(image))

    def _uniform_background_ratio(self, gray: np.ndarray) -> float:
        """Fraction of pixels close to the modal (most common) intensity."""
        hist = cv2.calcHist([gray], [0], None, [256], [0, 256]).flatten()
        modal_bin = int(np.argmax(hist))
        window = hist[max(0, modal_bin - 10): modal_bin + 10].sum()
        return float(window / gray.size)

    def _score_heuristic(self, image: np.ndarray) -> Dict[str, float]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        text_density = self._text_density(gray)
        aspect = self._aspect_ratio(image)
        color_var = self._color_variance(image)
        uniform_bg = self._uniform_background_ratio(gray)

        scores = {c: 0.0 for c in CATEGORIES}

        # Documents (invoice/receipt/id): high text density, low color variance,
        # often tall/portrait aspect ratio
        doc_signal = min(1.0, text_density / 3.0) * 0.5 + (1 - min(color_var / 90, 1.0)) * 0.5
        if aspect < 0.9:  # portrait-ish, receipt-like
            scores["invoice_receipt"] = round(doc_signal * 1.1, 3)
            scores["id_document"] = round(doc_signal * 0.7, 3)
        else:
            scores["invoice_receipt"] = round(doc_signal * 0.8, 3)
            scores["id_document"] = round(doc_signal * 0.6, 3)

        # Screenshots: very high uniform background ratio (flat UI colors),
        # moderate-to-high text density, near-16:9 or phone aspect ratios
        screenshot_signal = uniform_bg * 0.6 + min(1.0, text_density / 3.0) * 0.4
        scores["screenshot"] = round(screenshot_signal, 3)

        # Product / packaging: higher color variance, lower text density,
        # more "photographic" look
        product_signal = min(1.0, color_var / 90) * 0.6 + (1 - min(text_density / 3.0, 1.0)) * 0.4
        scores["product_damage"] = round(product_signal * 0.75, 3)
        scores["packaging"] = round(product_signal * 0.6, 3)

        scores["other"] = round(max(0.05, 1 - max(scores.values())), 3)

        return scores

    # ---------------------------- public API ---------------------------- #

    def classify(self, image: np.ndarray) -> ClassificationResult:
        if self.model is not None:
            try:
                scores = self.model.predict_proba(image)
            except Exception as exc:
                logger.warning("Model inference failed (%s); using heuristics.", exc)
                scores = self._score_heuristic(image)
        else:
            scores = self._score_heuristic(image)

        best_category = max(scores, key=scores.get)
        best_confidence = scores[best_category]

        return ClassificationResult(
            category=best_category,
            confidence=round(best_confidence, 3),
            scores=scores,
            routed_to=ROUTING_TABLE.get(best_category, "ai.agents.evidence_agent"),
        )

    def classify_from_path(self, path: str) -> ClassificationResult:
        image = cv2.imread(path, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"Could not decode image at: {path}")
        return self.classify(image)


# --------------------------------------------------------------------------- #
# Convenience function for pipeline integration
# --------------------------------------------------------------------------- #

def classify_complaint_image(path: str, model: Optional[ClassifierModel] = None) -> Dict[str, Any]:
    classifier = ImageClassifier(model=model)
    result = classifier.classify_from_path(path)
    return {
        "category": result.category,
        "confidence": result.confidence,
        "scores": result.scores,
        "routed_to": result.routed_to,
    }


if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) != 2:
        print("Usage: python image_classifier.py <image_path>")
        sys.exit(1)

    print(json.dumps(classify_complaint_image(sys.argv[1]), indent=2, default=str))
