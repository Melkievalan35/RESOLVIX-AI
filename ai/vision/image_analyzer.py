"""
image_analyzer.py
------------------
Core image analysis utilities for the AI complaint-resolution pipeline.

Responsibilities:
    - Load and validate uploaded images (from customer complaints / evidence)
    - Extract metadata (dimensions, format, size, EXIF)
    - Run basic quality checks (blur, brightness, resolution) so downstream
      agents (damage_detector, image_classifier) can trust the input or flag
      it for re-upload.

Dependencies:
    pip install opencv-python-headless pillow numpy
"""

from __future__ import annotations

import io
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

try:
    from PIL import Image, ExifTags
except ImportError:  # pragma: no cover
    Image = None
    ExifTags = None

logger = logging.getLogger("resolvix.ai.vision.image_analyzer")


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #

@dataclass
class ImageQualityReport:
    is_usable: bool
    blur_score: float
    brightness_score: float
    resolution_ok: bool
    width: int
    height: int
    issues: list = field(default_factory=list)


@dataclass
class ImageMetadata:
    filename: str
    format: str
    width: int
    height: int
    size_bytes: int
    mode: str
    exif: Dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

class AnalyzerConfig:
    MIN_WIDTH = 300
    MIN_HEIGHT = 300
    MIN_BLUR_VARIANCE = 100.0       # Laplacian variance threshold; lower = blurrier
    MIN_BRIGHTNESS = 25.0           # 0-255 scale
    MAX_BRIGHTNESS = 235.0
    ALLOWED_FORMATS = {"JPEG", "JPG", "PNG", "WEBP", "BMP"}
    MAX_FILE_SIZE_MB = 15


# --------------------------------------------------------------------------- #
# Core class
# --------------------------------------------------------------------------- #

class ImageAnalyzer:
    """
    Loads an image from disk or raw bytes and produces metadata + a quality
    report used to gate it into the rest of the AI vision pipeline
    (damage_detector.py, image_classifier.py).
    """

    def __init__(self, config: Optional[AnalyzerConfig] = None):
        self.config = config or AnalyzerConfig()
        if cv2 is None or Image is None:
            raise ImportError(
                "ImageAnalyzer requires opencv-python-headless and pillow. "
                "Install with: pip install opencv-python-headless pillow"
            )

    # ---------------------------- loading ---------------------------- #

    def load_from_path(self, path: str) -> np.ndarray:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Image not found: {path}")
        image = cv2.imread(path, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"Could not decode image at: {path}")
        return image

    def load_from_bytes(self, data: bytes) -> np.ndarray:
        arr = np.frombuffer(data, dtype=np.uint8)
        image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Could not decode image from bytes")
        return image

    # ---------------------------- metadata ---------------------------- #

    def extract_metadata(self, path: str) -> ImageMetadata:
        with Image.open(path) as img:
            exif_data = {}
            try:
                raw_exif = img._getexif()
                if raw_exif and ExifTags:
                    exif_data = {
                        ExifTags.TAGS.get(tag_id, tag_id): value
                        for tag_id, value in raw_exif.items()
                    }
            except (AttributeError, Exception):
                exif_data = {}

            return ImageMetadata(
                filename=os.path.basename(path),
                format=(img.format or "UNKNOWN").upper(),
                width=img.width,
                height=img.height,
                size_bytes=os.path.getsize(path),
                mode=img.mode,
                exif=exif_data,
            )

    def validate_format(self, metadata: ImageMetadata) -> Tuple[bool, Optional[str]]:
        if metadata.format not in self.config.ALLOWED_FORMATS:
            return False, f"Unsupported format: {metadata.format}"
        size_mb = metadata.size_bytes / (1024 * 1024)
        if size_mb > self.config.MAX_FILE_SIZE_MB:
            return False, f"File too large: {size_mb:.1f}MB (max {self.config.MAX_FILE_SIZE_MB}MB)"
        return True, None

    # ---------------------------- quality checks ---------------------------- #

    def _blur_score(self, gray: np.ndarray) -> float:
        """Higher variance of Laplacian = sharper image."""
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())

    def _brightness_score(self, gray: np.ndarray) -> float:
        return float(np.mean(gray))

    def assess_quality(self, image: np.ndarray) -> ImageQualityReport:
        h, w = image.shape[:2]
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        blur_score = self._blur_score(gray)
        brightness_score = self._brightness_score(gray)
        resolution_ok = w >= self.config.MIN_WIDTH and h >= self.config.MIN_HEIGHT

        issues = []
        if blur_score < self.config.MIN_BLUR_VARIANCE:
            issues.append("Image appears blurry")
        if brightness_score < self.config.MIN_BRIGHTNESS:
            issues.append("Image is too dark")
        elif brightness_score > self.config.MAX_BRIGHTNESS:
            issues.append("Image is overexposed")
        if not resolution_ok:
            issues.append(
                f"Resolution too low ({w}x{h}, min {self.config.MIN_WIDTH}x{self.config.MIN_HEIGHT})"
            )

        return ImageQualityReport(
            is_usable=len(issues) == 0,
            blur_score=round(blur_score, 2),
            brightness_score=round(brightness_score, 2),
            resolution_ok=resolution_ok,
            width=w,
            height=h,
            issues=issues,
        )

    # ---------------------------- orchestration ---------------------------- #

    def analyze(self, path: str) -> Dict[str, Any]:
        """
        Full pipeline: validate format -> load -> assess quality.
        Returns a dict ready to be attached to a complaint record / passed
        to the orchestrator agent.
        """
        metadata = self.extract_metadata(path)
        valid, format_error = self.validate_format(metadata)
        if not valid:
            return {
                "status": "rejected",
                "reason": format_error,
                "metadata": metadata.__dict__,
            }

        image = self.load_from_path(path)
        quality = self.assess_quality(image)

        status = "accepted" if quality.is_usable else "flagged_for_review"

        result = {
            "status": status,
            "metadata": metadata.__dict__,
            "quality": quality.__dict__,
        }
        logger.info("Analyzed image %s -> %s", metadata.filename, status)
        return result


# --------------------------------------------------------------------------- #
# Convenience function for pipeline integration
# --------------------------------------------------------------------------- #

def analyze_image(path: str) -> Dict[str, Any]:
    analyzer = ImageAnalyzer()
    return analyzer.analyze(path)

# Backward compatibility
analyze_complaint_image = analyze_image


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python image_analyzer.py <image_path>")
        sys.exit(1)

    result = analyze_complaint_image(sys.argv[1])
    import json
    print(json.dumps(result, indent=2, default=str))
