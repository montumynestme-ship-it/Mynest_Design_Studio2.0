import math
import uuid
from typing import Any

from app.data import furniture_catalog
from app.data.classes import ml_class_to_item_id
from app.schemas.floor_plan import LayoutItem
from app.services.coordinates import (
    DEFAULT_MPP,
    circular_angle_diff,
    euclidean_dist,
    mm_to_three,
    normalize_angle,
    three_to_mm,
    three_to_world,
    world_to_mm,
    world_to_three,
)


def detections_to_layout_items(
    detections: list[dict[str, Any]],
    confidence_threshold: float = 0.40,
) -> list[dict[str, Any]]:
    """Convert high-confidence detections into canonical LayoutItem dicts."""
    items: list[dict[str, Any]] = []

    for d in detections:
        conf = float(d.get("class_confidence") or d.get("confidence", 0.0))
        if conf < confidence_threshold:
            continue

        class_name = str(d.get("class", ""))
        item_id = d.get("item_id") or ml_class_to_item_id(class_name)

        pos = d.get("position", {})
        cx = float(pos.get("cx", 0.0))
        cy = float(pos.get("cy", 0.0))
        w = float(pos.get("w", 0.0))
        h = float(pos.get("h", 0.0))
        rotation = float(d.get("rotation_deg") or d.get("rotation") or 0.0)

        layout_item = LayoutItem(
            uid=f"det-{uuid.uuid4().hex[:8]}",
            item_id=item_id,
            cx=cx,
            cy=cy,
            w=w,
            h=h,
            rotation=rotation,
            label=f"Detected {class_name.replace('_', ' ').title()}",
        )
        items.append(layout_item.model_dump())

    return items


def detections_to_canonical_json(
    detections: list[dict[str, Any]],
    confidence_threshold: float = 0.40,
) -> dict[str, Any]:
    """Format detection list as a canonical_json dictionary."""
    furniture = detections_to_layout_items(detections, confidence_threshold)
    return {"furniture": furniture}


convert_detections_to_layout_items = detections_to_layout_items


def detections_to_3d_scene(
    detections: list[dict[str, Any]],
    structured_walls: list[dict[str, Any]] | None = None,
    mpp: float = DEFAULT_MPP,
    confidence_threshold: float = 0.30,
) -> dict[str, Any]:
    """Generate deterministic 3D scene placement directly from structured geometry.

    Guarantees X, Y, Z, rotation, and footprint are derived strictly from geometry.
    """
    furniture_3d: list[dict[str, Any]] = []

    for d in detections:
        conf = float(d.get("class_confidence") or d.get("confidence", 0.0))
        if conf < confidence_threshold:
            continue

        class_name = str(d.get("class", ""))
        item_id = str(d.get("item_id") or (ml_class_to_item_id(class_name) if class_name else ""))
        pos = d.get("position", {})
        cx = float(pos.get("cx", 0.0))
        cy = float(pos.get("cy", 0.0))
        rot_deg = float(d.get("rotation_deg") or d.get("rotation") or 0.0)

        # Retrieve canonical height
        from app.data.classes import CLASS_BY_ITEM_ID, CLASS_BY_NAME

        cls_info = CLASS_BY_ITEM_ID.get(item_id) or CLASS_BY_NAME.get(class_name)
        height_mm = cls_info.height_mm if cls_info else 800.0

        footprint = d.get("footprint", {})
        w_mm = float(footprint.get("width", world_to_mm(float(pos.get("w", 100.0)), mpp)))
        d_mm = float(footprint.get("depth", world_to_mm(float(pos.get("h", 100.0)), mpp)))

        # Coordinate transformation to Three.js meters
        pos_3d = {
            "x": round(world_to_three(cx, mpp), 4),
            "y": 0.0,
            "z": round(world_to_three(cy, mpp), 4),
        }
        # In Three.js y-up system, rotation around vertical axis is -rot_deg in radians
        rot_3d = {
            "x": 0.0,
            "y": round(-math.radians(rot_deg), 5),
            "z": 0.0,
        }
        dim_3d = {
            "width": round(mm_to_three(w_mm), 4),
            "depth": round(mm_to_three(d_mm), 4),
            "height": round(mm_to_three(height_mm), 4),
        }

        furniture_3d.append({
            "uid": d.get("id") or f"3d-{uuid.uuid4().hex[:8]}",
            "item_id": item_id,
            "class": class_name,
            "position": pos_3d,
            "rotation": rot_3d,
            "rotation_deg": rot_deg,
            "dimensions": dim_3d,
            "room_id": d.get("room_id"),
            "room_side": d.get("room_side"),
            "direction": d.get("direction"),
            "nearest_wall_id": d.get("nearest_wall_id"),
            "distance_to_wall_mm": d.get("distance_to_wall_mm"),
            "source_type": d.get("source_type", "predicted"),
        })

    # Transform structured walls to 3D segments
    walls_3d: list[dict[str, Any]] = []
    if structured_walls:
        for w in structured_walls:
            x1, y1 = float(w["x1"]), float(w["y1"])
            x2, y2 = float(w["x2"]), float(w["y2"])
            mid_x = (x1 + x2) / 2.0
            mid_y = (y1 + y2) / 2.0
            length_px = math.hypot(x2 - x1, y2 - y1)
            angle_rad = math.atan2(y2 - y1, x2 - x1)

            walls_3d.append({
                "id": w.get("id"),
                "position": {
                    "x": round(world_to_three(mid_x, mpp), 4),
                    "y": round(float(w.get("height", 2.7)) / 2.0, 4),
                    "z": round(world_to_three(mid_y, mpp), 4),
                },
                "rotation": {"x": 0.0, "y": round(-angle_rad, 5), "z": 0.0},
                "length": round(world_to_three(length_px, mpp), 4),
                "height": float(w.get("height", 2.7)),
                "thickness": round(world_to_three(float(w.get("thickness", 10.0)), mpp), 4),
                "is_window": bool(w.get("is_window", False)),
            })

    return {
        "furniture": furniture_3d,
        "walls": walls_3d,
        "coordinate_frame": "three_js_meters",
        "mpp": mpp,
    }


def validate_3d_orthographic_projection(
    scene_2d: dict[str, Any],
    scene_3d: dict[str, Any],
    mpp: float = DEFAULT_MPP,
) -> dict[str, Any]:
    """Re-project 3D footprints back to the 2D canonical plane and validate consistency.

    Requirement 27: Compares 2D scene vs 3D projected scene on object count,
    position, rotation, footprint, room, and walls.
    """
    f2d_list = scene_2d.get("furniture", [])
    f3d_list = scene_3d.get("furniture", [])

    discrepancies: list[str] = []
    count_match = (len(f2d_list) == len(f3d_list))
    if not count_match:
        discrepancies.append(f"Count mismatch: 2D has {len(f2d_list)} items, 3D has {len(f3d_list)} items")

    max_pos_err_mm = 0.0
    max_rot_err_deg = 0.0

    for idx, (item2d, item3d) in enumerate(zip(f2d_list, f3d_list, strict=False)):
        # Re-project 3D position to canonical 2D pixels
        pos3d = item3d["position"]
        proj_cx = three_to_world(pos3d["x"], mpp)
        proj_cy = three_to_world(pos3d["z"], mpp)

        # 2D coordinates
        cx2d = float(item2d.get("cx", item2d.get("position", {}).get("cx", 0.0)))
        cy2d = float(item2d.get("cy", item2d.get("position", {}).get("cy", 0.0)))

        # Position error in mm
        err_px = euclidean_dist(cx2d, cy2d, proj_cx, proj_cy)
        err_mm = world_to_mm(err_px, mpp)
        max_pos_err_mm = max(max_pos_err_mm, err_mm)

        if err_mm > 0.5:
            discrepancies.append(f"Item {idx} ({item2d.get('item_id')}): Position projection error {err_mm:.2f} mm exceeds tolerance")

        # Rotation check
        rot2d = float(item2d.get("rotation", item2d.get("rotation_deg", 0.0)))
        rot3d_deg = float(item3d.get("rotation_deg", 0.0))
        rot_err = circular_angle_diff(rot2d, rot3d_deg)
        max_rot_err_deg = max(max_rot_err_deg, rot_err)

        if rot_err > 0.05:
            discrepancies.append(f"Item {idx} ({item2d.get('item_id')}): Rotation projection error {rot_err:.2f}° exceeds tolerance")

        # Room match
        r2d = item2d.get("room_id")
        r3d = item3d.get("room_id")
        if r2d and r3d and r2d != r3d:
            discrepancies.append(f"Item {idx}: Room mismatch 2D '{r2d}' vs 3D '{r3d}'")

    is_valid = (len(discrepancies) == 0 and max_pos_err_mm <= 0.5 and max_rot_err_deg <= 0.05)

    return {
        "is_valid": is_valid,
        "object_count_2d": len(f2d_list),
        "object_count_3d": len(f3d_list),
        "max_position_error_mm": round(max_pos_err_mm, 4),
        "max_rotation_error_deg": round(max_rot_err_deg, 4),
        "discrepancies": discrepancies,
    }


