"""Ultralytics YOLO Detector Implementation for Floor-Plan Object Detection."""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from app.core.config import (
    ML_CONFIDENCE_THRESHOLD,
    ML_IMAGE_SIZE,
    ML_IOU_THRESHOLD,
    ML_MODEL_PATH,
    ML_MODEL_VERSION,
)
from app.data.classes import (
    CANONICAL_ML_CLASSES,
    CLASS_BY_ID,
    CLASS_NAMES,
    class_id_to_name,
)
from app.services.ml.annotation import GroundTruthAnnotation
from app.services.ml.detector import FloorPlanDetector

logger = logging.getLogger("app.services.ml.yolo_detector")


class YoloDetector(FloorPlanDetector):
    """Ultralytics YOLO object detector for 2D floor plans."""

    def __init__(self, model_path: str | Path | None = None) -> None:
        self.model_path = Path(model_path or ML_MODEL_PATH)
        self.model_version = ML_MODEL_VERSION
        self._model: Any = None
        self._is_obb = False
        self._load_model()

    def _load_model(self) -> None:
        """Load YOLO model lazily or initialize standard base detector."""
        try:
            from ultralytics import YOLO

            if self.model_path.exists():
                logger.info("Loading trained YOLO model from %s", self.model_path)
                self._model = YOLO(str(self.model_path))
            else:
                # Use lightweight standard base model for development/fallback
                logger.info("Custom weights %s not found. Initializing yolov8n.pt base model", self.model_path)
                self._model = YOLO("yolov8n.pt")

            # Check if model has OBB capabilities
            self._is_obb = "obb" in str(self.model_path).lower() or hasattr(self._model, "task") and self._model.task == "obb"
        except Exception as exc:
            logger.warning("Failed to initialize Ultralytics YOLO: %s. Using fallback detector.", exc)
            self._model = None

    def detect(
        self,
        image: str | Path | bytes | Image.Image,
        confidence_threshold: float = ML_CONFIDENCE_THRESHOLD,
        iou_threshold: float = ML_IOU_THRESHOLD,
    ) -> list[GroundTruthAnnotation]:
        """Run object detection on floor-plan image."""
        # Normalize image input to PIL Image
        pil_img: Image.Image
        if isinstance(image, Image.Image):
            pil_img = image
        elif isinstance(image, bytes):
            pil_img = Image.open(BytesIO(image)).convert("RGB")
        else:
            pil_img = Image.open(Path(image)).convert("RGB")

        w_img, h_img = pil_img.size

        if self._model is None:
            logger.warning("YOLO model unavailable, returning empty detections")
            return []

        try:
            results = self._model.predict(
                source=pil_img,
                conf=confidence_threshold,
                iou=iou_threshold,
                imgsz=ML_IMAGE_SIZE,
                verbose=False,
            )

            annotations: list[GroundTruthAnnotation] = []
            if not results or len(results) == 0:
                return []

            res = results[0]

            # Handle OBB detections
            if hasattr(res, "obb") and res.obb is not None and len(res.obb) > 0:
                # OBB returns xywhr (center x, center y, width, height, angle in radians)
                boxes = res.obb.xywhr.cpu().numpy()
                classes = res.obb.cls.cpu().numpy()
                confs = res.obb.conf.cpu().numpy()

                for box, cid, conf in zip(boxes, classes, confs, strict=False):
                    class_idx = int(cid)
                    if class_idx < len(CLASS_NAMES):
                        cname = CLASS_NAMES[class_idx]
                    else:
                        cname = class_id_to_name(class_idx) if class_idx in CLASS_BY_ID else "unknown"

                    cx, cy, bw, bh, angle_rad = float(box[0]), float(box[1]), float(box[2]), float(box[3]), float(box[4])
                    import math
                    deg = (math.degrees(angle_rad)) % 360.0

                    annotations.append(
                        GroundTruthAnnotation(
                            class_id=class_idx,
                            class_name=cname,
                            cx=cx,
                            cy=cy,
                            w=bw,
                            h=bh,
                            rotation=deg,
                            confidence=float(conf),
                        )
                    )
                return annotations

            # Handle standard 2D bounding boxes
            if hasattr(res, "boxes") and res.boxes is not None:
                boxes = res.boxes.xywh.cpu().numpy()  # cx, cy, w, h
                classes = res.boxes.cls.cpu().numpy()
                confs = res.boxes.conf.cpu().numpy()

                for box, cid, conf in zip(boxes, classes, confs, strict=False):
                    class_idx = int(cid)
                    if class_idx < len(CLASS_NAMES):
                        cname = CLASS_NAMES[class_idx]
                    else:
                        cname = class_id_to_name(class_idx) if class_idx in CLASS_BY_ID else "unknown"

                    cx, cy, bw, bh = float(box[0]), float(box[1]), float(box[2]), float(box[3])

                    # Aspect-ratio rotation heuristic for standard boxes:
                    # If width > height for an object whose canonical depth > width (like bed), infer 90 deg rotation
                    info = CLASS_BY_ID.get(class_idx)
                    rotation = 0.0
                    if info and info.has_meaningful_rotation:
                        canonical_ratio = info.width_mm / max(1.0, info.depth_mm)
                        detected_ratio = bw / max(1.0, bh)
                        if (canonical_ratio < 1.0 and detected_ratio > 1.2) or (canonical_ratio > 1.0 and detected_ratio < 0.8):
                            rotation = 90.0

                    annotations.append(
                        GroundTruthAnnotation(
                            class_id=class_idx,
                            class_name=cname,
                            cx=cx,
                            cy=cy,
                            w=bw,
                            h=bh,
                            rotation=rotation,
                            confidence=float(conf),
                        )
                    )

            return annotations

        except Exception as exc:
            logger.error("YOLO detection error: %s", exc)
            return []
