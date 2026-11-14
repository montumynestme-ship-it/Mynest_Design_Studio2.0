"""Geometric Interpretation & Spatial Reasoning Layer for Floor-Plan Detections.

Converts raw 2D object detections into rich spatial entities:
1. Exact coordinates & physical footprint (bbox + oriented footprint)
2. Direction determination adhering strictly to project convention (N=0°, E=90°, S=180°, W=270°)
3. Room side calculation relative to actual room geometry (left, center, right, top, middle, bottom, corner)
4. Wall relationship against actual architectural wall lines (nearest wall ID, distance, orientation, angle)
5. Object-to-object spatial relationships (left_of, right_of, in_front_of, near, adjacent_to, flanked_by)
6. Real-world physical dimensions using canonical Furniture Library priors
"""

from __future__ import annotations

import math
from typing import Any

from shapely.geometry import LineString, Point, Polygon

from app.data.classes import CLASS_BY_NAME, CANONICAL_ML_CLASSES
from app.services.coordinates import (
    DEFAULT_MPP,
    circular_angle_diff,
    direction_to_rotation,
    euclidean_dist,
    normalize_angle,
    rotation_to_direction,
    world_to_mm,
)


def calculate_room_side(
    cx: float,
    cy: float,
    room_polygon_or_bounds: list[tuple[float, float]] | dict[str, float] | tuple[float, float, float, float],
) -> dict[str, str]:
    """Calculate object position relative to room boundary geometry.

    Returns:
        {
            "room_side": "left" | "center" | "right" | "top" | "middle" | "bottom" | "corner",
            "room_side_detail": "top-left" | "bottom-right" | ...
        }
    """
    if isinstance(room_polygon_or_bounds, dict):
        x_min = float(room_polygon_or_bounds.get("x0", room_polygon_or_bounds.get("x_min", 0.0)))
        y_min = float(room_polygon_or_bounds.get("y0", room_polygon_or_bounds.get("y_min", 0.0)))
        x_max = float(room_polygon_or_bounds.get("x1", room_polygon_or_bounds.get("x_max", 1000.0)))
        y_max = float(room_polygon_or_bounds.get("y1", room_polygon_or_bounds.get("y_max", 1000.0)))
    elif isinstance(room_polygon_or_bounds, (list, tuple)) and len(room_polygon_or_bounds) == 4 and isinstance(room_polygon_or_bounds[0], (int, float)):
        x_min, y_min, x_max, y_max = [float(v) for v in room_polygon_or_bounds]
    elif isinstance(room_polygon_or_bounds, list) and len(room_polygon_or_bounds) >= 3:
        xs = [float(p[0]) for p in room_polygon_or_bounds]
        ys = [float(p[1]) for p in room_polygon_or_bounds]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
    else:
        return {"room_side": "center", "room_side_detail": "center"}

    room_w = max(1.0, x_max - x_min)
    room_h = max(1.0, y_max - y_min)

    # Relative coordinates normalized to [0, 1]
    u = max(0.0, min(1.0, (cx - x_min) / room_w))
    v = max(0.0, min(1.0, (cy - y_min) / room_h))

    # Horizontal position
    if u < 0.35:
        h_pos = "left"
    elif u > 0.65:
        h_pos = "right"
    else:
        h_pos = "center"

    # Vertical position
    if v < 0.35:
        v_pos = "top"
    elif v > 0.65:
        v_pos = "bottom"
    else:
        v_pos = "middle"

    # Detailed position
    if h_pos == "center" and v_pos == "middle":
        detail = "center"
    elif h_pos == "center":
        detail = v_pos
    elif v_pos == "middle":
        detail = h_pos
    else:
        detail = f"{v_pos}-{h_pos}"

    # Primary room_side determination
    # Extreme corners are identified when both dimensions are near room extremes
    is_corner = (u < 0.18 or u > 0.82) and (v < 0.18 or v > 0.82)
    if is_corner:
        primary = "corner"
    elif h_pos != "center" and v_pos == "middle":
        primary = h_pos
    elif v_pos != "middle" and h_pos == "center":
        primary = v_pos
    elif h_pos != "center" and v_pos != "middle":
        # Resolve which wall the object is closest to
        dist_h = min(u, 1.0 - u)
        dist_v = min(v, 1.0 - v)
        primary = h_pos if dist_h <= dist_v else v_pos
    elif h_pos != "center":
        primary = h_pos
    elif v_pos != "middle":
        primary = v_pos
    else:
        primary = "center"

    return {"room_side": primary, "room_side_detail": detail}


def calculate_wall_relationship(
    cx: float,
    cy: float,
    w: float,
    h: float,
    rotation_deg: float,
    structured_walls: list[dict[str, Any]],
    mpp: float = DEFAULT_MPP,
) -> dict[str, Any]:
    """Calculate relationship against actual architectural wall lines.

    Returns:
        nearest_wall_id, distance_to_wall_px, distance_to_wall_mm,
        wall_orientation, object_wall_angle, wall_relationship
    """
    if not structured_walls:
        return {
            "nearest_wall_id": None,
            "distance_to_wall_px": 9999.0,
            "distance_to_wall_mm": 99990.0,
            "wall_orientation": "none",
            "object_wall_angle": 0.0,
            "wall_relationship": "freestanding",
        }

    pt = Point(cx, cy)
    half_extent = min(float(w), float(h)) / 2.0

    min_dist = float("inf")
    nearest_wall: dict[str, Any] | None = None

    for w_seg in structured_walls:
        line = LineString([(float(w_seg["x1"]), float(w_seg["y1"])), (float(w_seg["x2"]), float(w_seg["y2"]))])
        dist = pt.distance(line)
        if dist < min_dist:
            min_dist = dist
            nearest_wall = w_seg

    if nearest_wall is None:
        return {
            "nearest_wall_id": None,
            "distance_to_wall_px": 9999.0,
            "distance_to_wall_mm": 99990.0,
            "wall_orientation": "none",
            "object_wall_angle": 0.0,
            "wall_relationship": "freestanding",
        }

    dist_mm = world_to_mm(min_dist, mpp)
    surface_dist_mm = max(0.0, dist_mm - world_to_mm(half_extent, mpp))

    # Calculate wall orientation
    wx1 = float(nearest_wall["x1"])
    wy1 = float(nearest_wall["y1"])
    wx2 = float(nearest_wall["x2"])
    wy2 = float(nearest_wall["y2"])
    wall_angle_raw = math.degrees(math.atan2(wy2 - wy1, wx2 - wx1)) % 180.0

    if wall_angle_raw < 15.0 or wall_angle_raw > 165.0:
        wall_orientation = "horizontal"
    elif 75.0 <= wall_angle_raw <= 105.0:
        wall_orientation = "vertical"
    else:
        wall_orientation = f"{round(wall_angle_raw, 1)}°"

    # Angle between object orientation and wall line [0, 90°]
    # (0° = parallel, 90° = perpendicular)
    angle_diff = circular_angle_diff(rotation_deg, wall_angle_raw)
    object_wall_angle = round(min(angle_diff, 180.0 - angle_diff), 1)
    if object_wall_angle > 90.0:
        object_wall_angle = round(180.0 - object_wall_angle, 1)

    # Adjacency check
    if surface_dist_mm <= 60.0:
        rel = "attached"
    elif surface_dist_mm <= 180.0:
        rel = "adjacent"
    else:
        rel = "freestanding"

    return {
        "nearest_wall_id": nearest_wall.get("id"),
        "distance_to_wall_px": round(min_dist, 2),
        "distance_to_wall_mm": round(dist_mm, 1),
        "wall_orientation": wall_orientation,
        "object_wall_angle": object_wall_angle,
        "wall_relationship": rel,
    }


def calculate_object_relationships(
    objects: list[dict[str, Any]],
    mpp: float = DEFAULT_MPP,
) -> list[dict[str, Any]]:
    """Derive geometric and spatial relationships between objects.

    Identifies:
    - side tables left_of / right_of a bed, or beds flanked_by side tables
    - center tables in_front_of sofas
    - dining chairs near / surrounding dining tables
    - chimneys adjacent_to / above kitchen base counters
    """
    by_room: dict[str, list[dict[str, Any]]] = {}
    for obj in objects:
        rid = obj.get("room_id") or "unassigned"
        by_room.setdefault(rid, []).append(obj)

    for rid, room_objs in by_room.items():
        for i, obj_a in enumerate(room_objs):
            a_id = obj_a.get("id") or f"obj_{i}"
            a_class = str(obj_a.get("class", ""))
            a_cx = float(obj_a["position"]["cx"])
            a_cy = float(obj_a["position"]["cy"])
            a_rot = float(obj_a.get("rotation_deg") or 0.0)

            relationships: list[dict[str, Any]] = []

            for j, obj_b in enumerate(room_objs):
                if i == j:
                    continue
                b_id = obj_b.get("id") or f"obj_{j}"
                b_class = str(obj_b.get("class", ""))
                b_cx = float(obj_b["position"]["cx"])
                b_cy = float(obj_b["position"]["cy"])

                dist_px = euclidean_dist(a_cx, a_cy, b_cx, b_cy)
                dist_mm = world_to_mm(dist_px, mpp)

                # Only evaluate relationships within 2.5 meters
                if dist_mm > 2500.0:
                    continue

                dx = a_cx - b_cx
                dy = a_cy - b_cy

                # 1. Side Table relative to Bed
                if a_class == "side_table" and b_class == "bed":
                    if abs(dx) > abs(dy):
                        rel_side = "left_of" if dx < 0 else "right_of"
                    else:
                        rel_side = "left_of" if dx < 0 else "right_of"
                    relationships.append({
                        "target_id": b_id,
                        "target_class": b_class,
                        "relationship": rel_side,
                        "distance_mm": round(dist_mm, 1),
                    })

                # 2. Bed flanked by Side Table
                elif a_class == "bed" and b_class == "side_table":
                    rel_side = "left" if dx > 0 else "right"
                    relationships.append({
                        "target_id": b_id,
                        "target_class": b_class,
                        "relationship": "flanked_by",
                        "direction": rel_side,
                        "distance_mm": round(dist_mm, 1),
                    })

                # 3. Center Table relative to Sofa
                elif a_class == "center_table" and "sofa" in b_class:
                    relationships.append({
                        "target_id": b_id,
                        "target_class": b_class,
                        "relationship": "in_front_of",
                        "distance_mm": round(dist_mm, 1),
                    })

                # 4. Sofa facing Center Table
                elif "sofa" in a_class and b_class == "center_table":
                    relationships.append({
                        "target_id": b_id,
                        "target_class": b_class,
                        "relationship": "faces",
                        "distance_mm": round(dist_mm, 1),
                    })

                # 5. Dining Chair relative to Dining Table
                elif a_class == "dining_chair" and b_class == "dining_table":
                    relationships.append({
                        "target_id": b_id,
                        "target_class": b_class,
                        "relationship": "arranged_around",
                        "distance_mm": round(dist_mm, 1),
                    })

                # 6. Chimney relative to Kitchen Base
                elif a_class == "chimney" and b_class == "kitchen_base":
                    relationships.append({
                        "target_id": b_id,
                        "target_class": b_class,
                        "relationship": "above_counter",
                        "distance_mm": round(dist_mm, 1),
                    })

                # 7. General proximity if very close
                elif dist_mm <= 400.0:
                    relationships.append({
                        "target_id": b_id,
                        "target_class": b_class,
                        "relationship": "adjacent_to",
                        "distance_mm": round(dist_mm, 1),
                    })

            obj_a["relationships"] = relationships

    return objects


def calculate_physical_footprint_and_dimensions(
    class_name: str,
    detected_w: float,
    detected_h: float,
    rotation_deg: float,
    mpp: float = DEFAULT_MPP,
    scale_available: bool = True,
) -> dict[str, Any]:
    """Calculate physical footprint and real-world dimensions using catalog priors."""
    class_info = CLASS_BY_NAME.get(class_name)

    det_w_mm = world_to_mm(detected_w, mpp)
    det_d_mm = world_to_mm(detected_h, mpp)

    if class_info is not None:
        lib_w_mm = float(class_info.width_mm)
        lib_d_mm = float(class_info.depth_mm)

        # If rotated 90 or 270, width and depth swap in visual footprint
        is_rotated_90 = round(rotation_deg % 180.0) in (90, 270)
        expected_w_vis = lib_d_mm if is_rotated_90 else lib_w_mm
        expected_d_vis = lib_w_mm if is_rotated_90 else lib_d_mm

        w_err = abs(det_w_mm - expected_w_vis) / max(1.0, expected_w_vis)
        d_err = abs(det_d_mm - expected_d_vis) / max(1.0, expected_d_vis)
        size_conf = max(0.2, min(0.99, 1.0 - (w_err + d_err) / 2.0))

        estimated_w_mm = lib_w_mm
        estimated_d_mm = lib_d_mm
    else:
        estimated_w_mm = det_w_mm
        estimated_d_mm = det_d_mm
        size_conf = 0.50

    status = "CALIBRATED" if scale_available else "ESTIMATED"

    return {
        "detected_width": round(detected_w, 2),
        "detected_height": round(detected_h, 2),
        "detected_width_mm": round(det_w_mm, 1),
        "detected_depth_mm": round(det_d_mm, 1),
        "estimated_width_mm": round(estimated_w_mm, 1),
        "estimated_depth_mm": round(estimated_d_mm, 1),
        "size_confidence": round(size_conf, 4),
        "dimensions_status": status,
        "footprint": {
            "width": round(estimated_w_mm, 1),
            "depth": round(estimated_d_mm, 1),
            "rotation_deg": round(rotation_deg, 1),
        },
    }
