from __future__ import annotations

import uuid
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from app.core.config import (
    ML_CONFIDENCE_THRESHOLD,
    ML_IOU_THRESHOLD,
    ML_MODEL_VERSION,
)
from app.data.classes import CLASS_BY_NAME, MLClassInfo, ml_class_to_item_id
from app.services.coordinates import (
    DEFAULT_MPP,
    DEFAULT_WORLD_SCALE,
    rotation_to_direction,
    world_to_mm,
)
from app.services.ml.annotation import GroundTruthAnnotation
from app.services.ml.detector import FloorPlanDetector
from app.services.ml.geometry_interpreter import (
    calculate_object_relationships,
    calculate_physical_footprint_and_dimensions,
    calculate_room_side,
    calculate_wall_relationship,
)
from app.services.ml.yolo_detector import YoloDetector


def _point_in_polygon(x: float, y: float, polygon: list[tuple[float, float]]) -> bool:
    """Ray casting algorithm for 2D point-in-polygon test."""
    n = len(polygon)
    if n < 3:
        return False
    inside = False
    p1x, p1y = polygon[0]
    for i in range(1, n + 1):
        p2x, p2y = polygon[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside


class FloorPlanInferenceService:
    """Orchestrates detection, coordinate normalization, spatial reasoning, and room/wall assignment."""

    def __init__(
        self,
        detector: FloorPlanDetector | None = None,
        mpp: float = DEFAULT_MPP,
        world_scale: float = DEFAULT_WORLD_SCALE,
    ) -> None:
        self.detector = detector or YoloDetector()
        self.mpp = mpp
        self.world_scale = world_scale

    def detect_objects(
        self,
        image_input: str | Path | bytes | Image.Image,
        room_polygons: dict[str, list[tuple[float, float]]] | None = None,
        structured_walls: list[dict[str, Any]] | None = None,
        confidence_threshold: float = ML_CONFIDENCE_THRESHOLD,
        iou_threshold: float = ML_IOU_THRESHOLD,
    ) -> list[dict[str, Any]]:
        """Detect furniture objects and return rich structured geometry JSON."""
        pil_img: Image.Image
        if isinstance(image_input, Image.Image):
            pil_img = image_input
        elif isinstance(image_input, bytes):
            pil_img = Image.open(BytesIO(image_input)).convert("RGB")
        else:
            pil_img = Image.open(Path(image_input)).convert("RGB")

        w_img, h_img = pil_img.size

        # 1. Run core shape detector
        raw_annotations = self.detector.detect(
            image=pil_img,
            confidence_threshold=confidence_threshold,
            iou_threshold=iou_threshold,
        )

        results: list[dict[str, Any]] = []

        for idx, anno in enumerate(raw_annotations):
            # 2. Coordinate normalization
            px_cx = round(anno.cx, 2)
            px_cy = round(anno.cy, 2)
            px_w = round(anno.w, 2)
            px_h = round(anno.h, 2)

            norm_cx = round(px_cx / max(1.0, w_img), 6)
            norm_cy = round(px_cy / max(1.0, h_img), 6)
            norm_w = round(px_w / max(1.0, w_img), 6)
            norm_h = round(px_h / max(1.0, h_img), 6)

            # Canonical World Pixels
            canon_cx = round(px_cx * self.world_scale, 2)
            canon_cy = round(px_cy * self.world_scale, 2)
            canon_w = round(px_w * self.world_scale, 2)
            canon_h = round(px_h * self.world_scale, 2)

            # 3. Room Assignment (Point-in-polygon)
            assigned_room_id: str | None = None
            assigned_room_poly: list[tuple[float, float]] | None = None
            room_assignment_method: str = "none"

            if room_polygons:
                for room_id, poly in room_polygons.items():
                    if _point_in_polygon(canon_cx, canon_cy, poly) or _point_in_polygon(px_cx, px_cy, poly):
                        assigned_room_id = room_id
                        assigned_room_poly = poly
                        room_assignment_method = "polygon"
                        break

            # 4. Room Side Calculation
            room_side_val = "center"
            room_side_detail_val = "center"
            if assigned_room_poly:
                side_info = calculate_room_side(canon_cx, canon_cy, assigned_room_poly)
                room_side_val = side_info["room_side"]
                room_side_detail_val = side_info["room_side_detail"]

            # 5. Rotation & Direction (N/E/S/W)
            class_info = CLASS_BY_NAME.get(anno.class_name)
            rotation_val: float | None = None
            rotation_status: str = "NOT_VALIDATED"
            direction_val: str | None = None

            if class_info and class_info.has_meaningful_rotation:
                rotation_val = round(anno.rotation % 360.0, 1)
                rotation_status = "VALIDATED"
                direction_val = rotation_to_direction(rotation_val, cardinal_only=True)
            elif anno.rotation != 0.0:
                rotation_val = round(anno.rotation % 360.0, 1)
                rotation_status = "ESTIMATED"
                direction_val = rotation_to_direction(rotation_val, cardinal_only=True)
            else:
                rotation_val = 0.0
                rotation_status = "NOT_VALIDATED"
                direction_val = "N"

            # 6. Wall Relationship
            wall_rel = calculate_wall_relationship(
                cx=canon_cx,
                cy=canon_cy,
                w=canon_w,
                h=canon_h,
                rotation_deg=rotation_val or 0.0,
                structured_walls=structured_walls or [],
                mpp=self.mpp,
            )

            # 7. Physical Footprint & Real-World Dimensions
            dim_info = calculate_physical_footprint_and_dimensions(
                class_name=anno.class_name,
                detected_w=canon_w,
                detected_h=canon_h,
                rotation_deg=rotation_val or 0.0,
                mpp=self.mpp,
                scale_available=True,
            )

            # 8. Separate confidence scores
            class_conf = round(anno.confidence, 4)
            pos_conf = 0.95 if class_conf >= 0.20 else round(class_conf * 1.5, 4)
            rot_conf = 0.90 if rotation_status == "VALIDATED" else 0.50
            size_conf = dim_info["size_confidence"]

            val_status = "REVIEW_REQUIRED" if (class_conf < 0.20 or size_conf < 0.30) else "PASS"

            item_id = ml_class_to_item_id(anno.class_name)

            record = {
                "id": f"prediction_{idx + 1:03d}",
                "class": anno.class_name,
                "class_id": anno.class_id,
                "item_id": item_id,
                "class_confidence": class_conf,
                "position_confidence": pos_conf,
                "rotation_confidence": rot_conf,
                "size_confidence": size_conf,
                "confidence": class_conf,  # backwards-compatible
                "position": {
                    "cx": canon_cx,
                    "cy": canon_cy,
                    "w": canon_w,
                    "h": canon_h,
                    "coordinate_frame": "canonical_world_px",
                },
                "bbox": {
                    "x1": round(canon_cx - canon_w / 2.0, 2),
                    "y1": round(canon_cy - canon_h / 2.0, 2),
                    "x2": round(canon_cx + canon_w / 2.0, 2),
                    "y2": round(canon_cy + canon_h / 2.0, 2),
                },
                "footprint": dim_info["footprint"],
                "normalized": {
                    "cx": norm_cx,
                    "cy": norm_cy,
                    "w": norm_w,
                    "h": norm_h,
                },
                "image_pixels": {
                    "cx": px_cx,
                    "cy": px_cy,
                    "w": px_w,
                    "h": px_h,
                },
                "dimensions_mm": {
                    "width": dim_info["estimated_width_mm"],
                    "depth": dim_info["estimated_depth_mm"],
                    "detected_width_mm": dim_info["detected_width_mm"],
                    "detected_depth_mm": dim_info["detected_depth_mm"],
                    "status": dim_info["dimensions_status"],
                },
                "rotation": rotation_val,
                "rotation_deg": rotation_val,
                "rotation_status": rotation_status,
                "direction": direction_val,
                "room_id": assigned_room_id,
                "room_assignment_method": room_assignment_method,
                "room_side": room_side_val,
                "room_side_detail": room_side_detail_val,
                "nearest_wall_id": wall_rel["nearest_wall_id"],
                "distance_to_wall_px": wall_rel["distance_to_wall_px"],
                "distance_to_wall_mm": wall_rel["distance_to_wall_mm"],
                "wall_orientation": wall_rel["wall_orientation"],
                "object_wall_angle": wall_rel["object_wall_angle"],
                "wall_relationship": wall_rel["wall_relationship"],
                "relationships": [],
                "source_type": "predicted",
                "validation_status": val_status,
                "model_version": ML_MODEL_VERSION,
            }
            results.append(record)

        # 9. Compute multi-object spatial relationships within each room
        results = calculate_object_relationships(results, self.mpp)

        return results

