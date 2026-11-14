"""Base Detector Interface for MyNest ML Object Detection."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from PIL import Image

from app.services.ml.annotation import GroundTruthAnnotation


class FloorPlanDetector(ABC):
    """Abstract interface for all floor-plan object detectors."""

    @abstractmethod
    def detect(
        self,
        image: str | Path | bytes | Image.Image,
        confidence_threshold: float = 0.35,
        iou_threshold: float = 0.50,
    ) -> list[GroundTruthAnnotation]:

        """Run object detection on a floor-plan image and return list of detected annotations."""
        raise NotImplementedError
