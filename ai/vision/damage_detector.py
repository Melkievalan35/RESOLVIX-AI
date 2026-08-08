"""
damage_detector.py
-------------------
Detects and localizes physical damage (cracks, dents, tears, stains,
scratches) in product images submitted as complaint evidence.

Two modes are supported:
    1. Heuristic mode (default, no training required): classical CV
       techniques (edge density, contour irregularity, color-anomaly
       blobs) produce a damage score + bounding boxes. Works out of the
       box and is useful as a baseline / fallback.
    2. Model mode (optional): if a trained detection model (e.g. a
       fine-tuned YOLO / torchvision detector) is available, plug it in
       via `DamageDetector(model=...)` and it will be used instead.

Dependencies:
    pip install opencv-python-headless numpy
    # optional, for model mode:
    pip install torch torchvision
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Protocol

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

logger = logging.getLogger("resolvix.ai.vision.damage_detector")


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #

@dataclass
class DamageRegion:
    label: str              # e.g. "crack", "dent", "stain", "tear", "scratch"
    confidence: float       # 0-1
    bbox: List[int]         # [x, y, w, h]
    area_ratio: float       # fraction of total image area


@dataclass
class DamageReport:
    damage_detected: bool
    severity: str            # "none" | "minor" | "moderate" | "severe"
    damage_score: float      # 0-1 aggregate score
    regions: List[DamageRegion] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


class DetectionModel(Protocol):
    """Interface any pluggable deep-learning damage model must satisfy."""

    def predict(self, image: np.ndarray) -> List[DamageRegion]:
        ...


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

class DamageDetectorConfig:
    CANNY_LOW = 50
    CANNY_HIGH = 150
    MIN_CONTOUR_AREA = 150          # ignore tiny noise contours
    EDGE_DENSITY_MINOR = 0.02       # fraction of edge pixels -> minor damage
    EDGE_DENSITY_MODERATE = 0.05
    EDGE_DENSITY_SEVERE = 0.10
    IRREGULARITY_THRESHOLD = 0.35   # contour solidity below this = irregular/damaged shape


# --------------------------------------------------------------------------- #
# Core class
# --------------------------------------------------------------------------- #

class DamageDetector:
    """
    Detects damage in a product image. Falls back to classical CV
    heuristics unless a trained `model` is supplied.
    """

    def __init__(
        self,
        config: Optional[DamageDetectorConfig] = None,
        model: Optional[DetectionModel] = None,
    ):
        if cv2 is None:
            raise ImportError("DamageDetector requires opencv-python-headless.")
        self.config = config or DamageDetectorConfig()
        self.model = model  # optional deep-learning model, plugged in externally

    # ---------------------------- heuristic pipeline ---------------------------- #

    def _preprocess(self, image: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        return gray

    def _edge_density(self, edges: np.ndarray) -> float:
        return float(np.count_nonzero(edges)) / edges.size

    def _find_candidate_regions(self, image: np.ndarray, edges: np.ndarray) -> List[DamageRegion]:
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        h, w = image.shape[:2]
        total_area = h * w

        regions: List[DamageRegion] = []
        for c in contours:
            area = cv2.contourArea(c)
            if area < self.config.MIN_CONTOUR_AREA:
                continue

            x, y, bw, bh = cv2.boundingRect(c)
            hull = cv2.convexHull(c)
            hull_area = cv2.contourArea(hull)
            solidity = area / hull_area if hull_area > 0 else 1.0

            # Irregular (low-solidity) shapes are more likely to be
            # cracks/tears than clean product edges/labels.
            if solidity < self.config.IRREGULARITY_THRESHOLD:
                label = "crack_or_tear"
                confidence = round(min(0.95, 1.0 - solidity), 2)
            else:
                label = "surface_mark"
                confidence = round(0.4 + (area / total_area) * 5, 2)
                confidence = min(confidence, 0.85)

            regions.append(
                DamageRegion(
                    label=label,
                    confidence=confidence,
                    bbox=[int(x), int(y), int(bw), int(bh)],
                    area_ratio=round(area / total_area, 4),
                )
            )

        # Keep the most significant regions only
        regions.sort(key=lambda r: r.confidence, reverse=True)
        return regions[:10]

    def _severity_from_score(self, score: float) -> str:
        cfg = self.config
        if score < cfg.EDGE_DENSITY_MINOR:
            return "none"
        if score < cfg.EDGE_DENSITY_MODERATE:
            return "minor"
        if score < cfg.EDGE_DENSITY_SEVERE:
            return "moderate"
        return "severe"

    def _detect_heuristic(self, image: np.ndarray) -> DamageReport:
        gray = self._preprocess(image)
        edges = cv2.Canny(gray, self.config.CANNY_LOW, self.config.CANNY_HIGH)

        density = self._edge_density(edges)
        severity = self._severity_from_score(density)
        regions = self._find_candidate_regions(image, edges)

        notes = []
        if severity == "none":
            notes.append("No significant damage indicators detected.")
        else:
            notes.append(
                f"Detected {len(regions)} candidate damage region(s) "
                f"with edge density {density:.3f}."
            )

        return DamageReport(
            damage_detected=severity != "none",
            severity=severity,
            damage_score=round(min(density * 8, 1.0), 3),  # normalize roughly to 0-1
            regions=regions,
            notes=notes,
        )

    # ---------------------------- model pipeline ---------------------------- #

    def _detect_with_model(self, image: np.ndarray) -> DamageReport:
        regions = self.model.predict(image)
        if not regions:
            return DamageReport(
                damage_detected=False,
                severity="none",
                damage_score=0.0,
                regions=[],
                notes=["Model found no damage regions."],
            )

        max_conf = max(r.confidence for r in regions)
        if max_conf < 0.3:
            severity = "minor"
        elif max_conf < 0.6:
            severity = "moderate"
        else:
            severity = "severe"

        return DamageReport(
            damage_detected=True,
            severity=severity,
            damage_score=round(max_conf, 3),
            regions=regions,
            notes=[f"Model detected {len(regions)} region(s)."],
        )

    # ---------------------------- public API ---------------------------- #

    def detect(self, image: np.ndarray) -> DamageReport:
        if self.model is not None:
            try:
                return self._detect_with_model(image)
            except Exception as exc:  # fall back gracefully
                logger.warning("Model inference failed (%s); falling back to heuristics.", exc)
        return self._detect_heuristic(image)

    def detect_from_path(self, path: str) -> DamageReport:
        image = cv2.imread(path, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"Could not decode image at: {path}")
        return self.detect(image)


# --------------------------------------------------------------------------- #
# Convenience function for pipeline integration
# --------------------------------------------------------------------------- #

def detect_damage(path: str, model: Optional[DetectionModel] = None) -> Dict[str, Any]:
    detector = DamageDetector(model=model)
    report = detector.detect_from_path(path)
    return {
        "damage_detected": report.damage_detected,
        "severity": report.severity,
        "damage_score": report.damage_score,
        "regions": [asdict(r) for r in report.regions],
        "notes": report.notes,
    }


if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) != 2:
        print("Usage: python damage_detector.py <image_path>")
        sys.exit(1)

    print(json.dumps(detect_damage(sys.argv[1]), indent=2, default=str))
