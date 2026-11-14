"""Explicit coordinate system transformations and angle arithmetic.

Coordinate Spaces:
- PDF Points: Native pdfplumber / PDF units (72 DPI, top-left origin, y-down).
- Image Pixels: Rasterized floor plan image pixels.
- Canonical World Px: Authoritative scene coordinate frame in canonical_json (scale = 2.0).
- Millimeters (mm): Real-world physical dimensions.
- Three.js Meters (m): 3D engine world units where 1.0 = 1 metre.
"""

from typing import Any

DEFAULT_WORLD_SCALE = 2.0
DEFAULT_MPP = 0.01  # 1 pixel = 10 mm = 0.01 metres


def pdf_to_image(x: float, y: float, scale: float = DEFAULT_WORLD_SCALE) -> tuple[float, float]:
    """Convert PDF points to image pixels at given scale."""
    return (float(x) * scale, float(y) * scale)


def image_to_world(
    x: float, y: float, image_scale: float = 1.0, world_scale: float = DEFAULT_WORLD_SCALE
) -> tuple[float, float]:
    """Map raster image coordinates back to canonical world pixels."""
    factor = world_scale / (image_scale or 1.0)
    return (float(x) * factor, float(y) * factor)


def world_to_mm(px: float, mpp: float = DEFAULT_MPP) -> float:
    """Convert canonical world pixels to millimeters."""
    return float(px) * mpp * 1000.0


def mm_to_world(mm: float, mpp: float = DEFAULT_MPP) -> float:
    """Convert millimeters to canonical world pixels."""
    return float(mm) / (mpp * 1000.0)


def mm_to_three(mm: float) -> float:
    """Convert millimeters to Three.js meters."""
    return float(mm) / 1000.0


def three_to_mm(m: float) -> float:
    """Convert Three.js meters to millimeters."""
    return float(m) * 1000.0


def world_to_three(px: float, mpp: float = DEFAULT_MPP) -> float:
    """Convert canonical world pixels directly to Three.js meters."""
    return float(px) * mpp


def three_to_world(m: float, mpp: float = DEFAULT_MPP) -> float:
    """Convert Three.js meters back to canonical world pixels."""
    return float(m) / mpp


def normalize_angle(deg: float) -> float:
    """Normalize any degree angle into [0, 360)."""
    return float(deg) % 360.0


def circular_angle_diff(deg1: float, deg2: float) -> float:
    """Calculate minimal circular angle difference in degrees in range [0, 180].

    Example:
        circular_angle_diff(359.0, 1.0) -> 2.0
        circular_angle_diff(90.0, 270.0) -> 180.0
    """
    diff = abs(normalize_angle(deg1) - normalize_angle(deg2))
    return min(diff, 360.0 - diff)


# Canonical Direction Mapping
# N = 0° (Facing Up)
# E = 90° (Facing Right)
# S = 180° (Facing Down)
# W = 270° (Facing Left)
DIRECTION_TO_ROTATION: dict[str, float] = {
    "N": 0.0,
    "E": 90.0,
    "S": 180.0,
    "W": 270.0,
    "NE": 45.0,
    "SE": 135.0,
    "SW": 225.0,
    "NW": 315.0,
}


def direction_to_rotation(direction: str) -> float:
    """Convert a N/E/S/W direction string to its canonical rotation in degrees."""
    d = direction.strip().upper()
    if d not in DIRECTION_TO_ROTATION:
        raise ValueError(f"Unknown direction '{direction}'. Expected one of {list(DIRECTION_TO_ROTATION.keys())}.")
    return DIRECTION_TO_ROTATION[d]


def rotation_to_direction(deg: float, cardinal_only: bool = True) -> str:
    """Convert any rotation angle in degrees to its canonical N/E/S/W direction string.

    Quadrant convention (cardinal_only=True):
    - [315°, 360°) ∪ [0°, 45°) -> "N"
    - [45°, 135°)             -> "E"
    - [135°, 225°)            -> "S"
    - [225°, 315°)            -> "W"
    """
    angle = normalize_angle(deg)
    if cardinal_only:
        if angle >= 315.0 or angle < 45.0:
            return "N"
        if 45.0 <= angle < 135.0:
            return "E"
        if 135.0 <= angle < 225.0:
            return "S"
        return "W"

    # 8-wind resolution
    if angle >= 337.5 or angle < 22.5:
        return "N"
    if 22.5 <= angle < 67.5:
        return "NE"
    if 67.5 <= angle < 112.5:
        return "E"
    if 112.5 <= angle < 157.5:
        return "SE"
    if 157.5 <= angle < 202.5:
        return "S"
    if 202.5 <= angle < 247.5:
        return "SW"
    if 247.5 <= angle < 292.5:
        return "W"
    return "NW"


def is_cardinal_direction(direction: str) -> bool:
    """Check if string is a valid N/E/S/W cardinal direction."""
    return direction.strip().upper() in ("N", "E", "S", "W")



def euclidean_dist(x1: float, y1: float, x2: float, y2: float) -> float:
    """Euclidean distance between two 2D points."""
    import math

    return math.hypot(float(x2) - float(x1), float(y2) - float(y1))


def transform_box_to_canonical(
    box: dict[str, Any], src_frame: str, scale: float = DEFAULT_WORLD_SCALE, mpp: float = DEFAULT_MPP
) -> dict[str, Any]:
    """Convert any detected bounding box into canonical world pixels."""
    cx = float(box["cx"])
    cy = float(box["cy"])
    w = float(box["w"])
    h = float(box["h"])

    if src_frame == "pdf":
        cx, cy = pdf_to_image(cx, cy, scale)
        w, h = w * scale, h * scale
    elif src_frame == "image":
        cx, cy = image_to_world(cx, cy, 1.0, scale)
    elif src_frame == "three":
        cx = three_to_world(cx, mpp)
        cy = three_to_world(cy, mpp)
        w = three_to_world(w, mpp)
        h = three_to_world(h, mpp)

    result = dict(box)
    result["cx"] = round(cx, 2)
    result["cy"] = round(cy, 2)
    result["w"] = round(w, 2)
    result["h"] = round(h, 2)
    result["coordinate_frame"] = "canonical_world_px"
    return result
