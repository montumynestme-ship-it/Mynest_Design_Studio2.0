"""Ground-truth annotation serializer for ML floor-plan object detection.

Supports:
1. Standard YOLO detection format: <class_id> <cx_norm> <cy_norm> <w_norm> <h_norm>
2. YOLO OBB (Oriented Bounding Box) format: <class_id> <x1> <y1> <x2> <y2> <x3> <y3> <x4> <y4>
3. Canonical structured JSON for ground-truth comparison and evaluation.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from app.data.classes import class_name_to_id, item_id_to_ml_class
from app.services.coordinates import normalize_angle


@dataclass
class GroundTruthAnnotation:
    """Represents a single ground-truth or detected object annotation."""

    class_id: int
    class_name: str
    cx: float  # center X in pixels
    cy: float  # center Y in pixels
    w: float   # width in pixels
    h: float   # height in pixels
    rotation: float = 0.0  # rotation in degrees [0, 360)
    room_id: str | None = None
    confidence: float = 1.0

    def to_yolo_bbox(self, img_w: float, img_h: float) -> tuple[int, float, float, float, float]:
        """Return (class_id, cx_norm, cy_norm, w_norm, h_norm) normalized to [0, 1]."""
        cx_norm = max(0.0, min(1.0, self.cx / max(1.0, img_w)))
        cy_norm = max(0.0, min(1.0, self.cy / max(1.0, img_h)))
        w_norm = max(0.0, min(1.0, self.w / max(1.0, img_w)))
        h_norm = max(0.0, min(1.0, self.h / max(1.0, img_h)))
        return (self.class_id, cx_norm, cy_norm, w_norm, h_norm)

    def to_yolo_line(self, img_w: float, img_h: float) -> str:
        """Format as standard YOLO txt format: <class_id> <cx> <cy> <w> <h>."""
        cid, cx, cy, w, h = self.to_yolo_bbox(img_w, img_h)
        return f"{cid} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"

    def get_rotated_corners(self) -> list[tuple[float, float]]:
        """Calculate the 4 corner points (x, y) of the oriented bounding box in pixels."""
        rad = math.radians(normalize_angle(self.rotation))
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)

        hw = self.w / 2.0
        hh = self.h / 2.0

        # Unrotated local corners relative to center: top-left, top-right, bottom-right, bottom-left
        local_corners = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
        corners: list[tuple[float, float]] = []

        for lx, ly in local_corners:
            # Rotate by rad
            rx = lx * cos_a - ly * sin_a
            ry = lx * sin_a + ly * cos_a
            corners.append((self.cx + rx, self.cy + ry))

        return corners

    def to_yolo_obb_line(self, img_w: float, img_h: float) -> str:
        """Format as YOLO OBB format: <class_id> <x1> <y1> <x2> <y2> <x3> <y3> <x4> <y4>."""
        corners = self.get_rotated_corners()
        norm_coords: list[str] = []
        for x, y in corners:
            nx = max(0.0, min(1.0, x / max(1.0, img_w)))
            ny = max(0.0, min(1.0, y / max(1.0, img_h)))
            norm_coords.extend([f"{nx:.6f}", f"{ny:.6f}"])
        return f"{self.class_id} " + " ".join(norm_coords)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GroundTruthAnnotation:
        """Construct from dictionary."""
        return cls(
            class_id=int(data["class_id"]),
            class_name=str(data["class_name"]),
            cx=float(data["cx"]),
            cy=float(data["cy"]),
            w=float(data["w"]),
            h=float(data["h"]),
            rotation=float(data.get("rotation", 0.0)),
            room_id=data.get("room_id"),
            confidence=float(data.get("confidence", 1.0)),
        )

    @classmethod
    def from_layout_item(
        cls,
        item: dict[str, Any],
        room_id: str | None = None,
    ) -> GroundTruthAnnotation | None:
        """Construct from a canvas PlacedItem or canonical LayoutItem."""
        item_id = item.get("item_id") or (item.get("item", {}).get("id") if isinstance(item.get("item"), dict) else None)
        if not item_id:
            return None

        ml_class = item_id_to_ml_class(item_id)
        if not ml_class:
            return None

        class_id = class_name_to_id(ml_class)
        cx = float(item.get("cx", item.get("x", 0.0)))
        cy = float(item.get("cy", item.get("y", 0.0)))
        w = float(item.get("w", 0.0))
        h = float(item.get("h", 0.0))
        rotation = float(item.get("rotation", 0.0))

        return cls(
            class_id=class_id,
            class_name=ml_class,
            cx=cx,
            cy=cy,
            w=w,
            h=h,
            rotation=normalize_angle(rotation),
            room_id=room_id,
            confidence=1.0,
        )
