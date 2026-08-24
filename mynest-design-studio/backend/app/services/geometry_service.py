"""Deterministic geometry engine (pure, side-effect-free functions).

Mirrored on the frontend in `src/lib/geometry.ts`. All spatial units are
millimetres unless noted. These functions are the authoritative spatial
math per PRD §20 and must never depend on AI output.
"""

import math
from collections.abc import Sequence

Point = tuple[float, float]


class OrientedRect:
    """Axis-aligned-in-local-space rectangle with a center, size and rotation."""

    __slots__ = ("cx", "cy", "w", "h", "rotation")

    def __init__(self, cx: float, cy: float, w: float, h: float, rotation: float) -> None:
        self.cx = cx
        self.cy = cy
        self.w = w
        self.h = h
        self.rotation = rotation


def calculate_room_area_m2(polygon: Sequence[Point]) -> float:
    """Shoelace formula. Input vertices in mm; output area in m²."""
    n = len(polygon)
    if n < 3:
        return 0.0
    total = 0.0
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return abs(total) / (2 * 1_000_000)


def rect_corners(rect: OrientedRect) -> list[Point]:
    r = math.radians(rect.rotation)
    cos_r, sin_r = math.cos(r), math.sin(r)
    hw, hh = rect.w / 2, rect.h / 2
    local = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
    return [
        (rect.cx + lx * cos_r - ly * sin_r, rect.cy + lx * sin_r + ly * cos_r) for lx, ly in local
    ]


def _project(corners: list[Point], axis: Point) -> tuple[float, float]:
    dots = [cx * axis[0] + cy * axis[1] for cx, cy in corners]
    return min(dots), max(dots)


def rects_collide(a: OrientedRect, b: OrientedRect) -> bool:
    """Separating Axis Theorem overlap test for two oriented rectangles."""
    corners_a = rect_corners(a)
    corners_b = rect_corners(b)
    for corners in (corners_a, corners_b):
        for i in range(4):
            x1, y1 = corners[i]
            x2, y2 = corners[(i + 1) % 4]
            axis = (-(y2 - y1), x2 - x1)  # edge normal
            a_min, a_max = _project(corners_a, axis)
            b_min, b_max = _project(corners_b, axis)
            if a_max < b_min or b_max < a_min:
                return False  # found a separating axis
    return True


def point_in_polygon(point: Point, polygon: Sequence[Point]) -> bool:
    """Ray-casting point-in-polygon test."""
    x, y = point
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def rect_polygon_min_distance(rect: OrientedRect, polygon: Sequence[Point]) -> float:
    """Approximate min distance (mm) between a rect's corners and a polygon's
    edges; 0 if the rect center is inside the polygon."""
    if point_in_polygon((rect.cx, rect.cy), polygon):
        return 0.0
    corners = rect_corners(rect)
    best = math.inf
    n = len(polygon)
    for cx, cy in corners:
        for i in range(n):
            best = min(best, _point_segment_distance((cx, cy), polygon[i], polygon[(i + 1) % n]))
    return best


def _point_segment_distance(p: Point, a: Point, b: Point) -> float:
    px, py = p
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))
