"""PROTOTYPE — perspective structural (edge) pass from the canonical 3D scene.

Why this exists: the backend geometry *canvas* (``render_control_image``) is TOP-DOWN, but
the AI base render is a PERSPECTIVE 3/4 capture, so the top-down canvas cannot be used as a
projection-consistent geometry conditioner (see the integration report). This module renders
the SAME canonical geometry (room boundary walls + furniture boxes) through the SAME camera
the frontend uses for the base render (``solveAiCamera`` / ``AI_FOV`` / the 1216×832 capture
aspect, ported faithfully from ``frontend/src/lib/aiCamera.ts`` + ``RoomScene3D.tsx``), and
draws it as a clean line/edge map — the artifact that a Canny/depth ControlNet would need.

Status / honesty:
* OFFLINE, deterministic, no fal, no paid calls. It is a PROTOTYPE conditioning artifact,
  NOT wired into the live generation request.
* Canonical geometry is READ-ONLY: furniture identity/position/dimensions/rotation and the
  room boundary are projected as-is; nothing is moved, resized, or invented.
* Camera parity: the dollhouse camera (position/target/FOV/aspect) is a faithful port, so the
  projection is of the same composition. Pixel-exact alignment with the Three.js base render
  is NOT guaranteed (the frontend also has an enclosed eye-level mode, an 18% dollhouse pad,
  and real mesh geometry). The production-exact path is to render this pass inside the same
  RoomScene3D as a wireframe. This module proves the approach offline.
"""

from __future__ import annotations

import math
from io import BytesIO
from typing import Any

from PIL import Image, ImageDraw

from app.data.classes import CLASS_BY_ITEM_ID

# Ported constants (single source of truth in frontend/src/lib/aiCamera.ts + scene.ts).
AI_FOV = 46.0                 # vertical FOV, degrees (dollhouse base capture)
BASE_CAPTURE_W = 1216
BASE_CAPTURE_H = 832
_DEG = math.pi / 180.0
_WALL_HEIGHT_M = 2.7          # matches the scene's structured-wall height
_DEFAULT_FURN_HEIGHT_M = 0.8  # when the item carries no catalog height

Vec3 = tuple[float, float, float]


# ── small pure-Python 3D math (no numpy dependency) ────────────────────────────────
def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a: Vec3) -> Vec3:
    n = math.sqrt(_dot(a, a)) or 1.0
    return (a[0] / n, a[1] / n, a[2] / n)


def compute_mpp(rooms: list[dict[str, Any]]) -> float:
    """Metres per plan pixel — ported from frontend lib/scene.ts computeMpp.

    Items missing dimensions are skipped (fail-safe) rather than crashing the calibration.
    """
    def _dim(f: dict[str, Any]) -> float | None:
        w, h = f.get("w"), f.get("h")
        if w is None or h is None:
            return None
        return max(float(w), float(h))

    for r in rooms:
        for f in r.get("furniture", []) or []:
            if "bed" in str(f.get("item_id", "")):
                d = _dim(f)
                if d:
                    return 2.0 / d
    for r in rooms:
        for f in r.get("furniture", []) or []:
            if str(f.get("item_id", "")) == "side-table":
                d = _dim(f)
                if d:
                    return 0.45 / d
    return 0.01


def _furniture_points(furniture: list[dict[str, Any]], cx: float, cy: float, mpp: float) -> list[tuple[float, float]]:
    """The 4 rotated corners (metres, x/z relative to room centre) of each non-opening
    item — exactly the set RoomScene3D feeds solveAiCamera."""
    pts: list[tuple[float, float]] = []
    for f in furniture:
        iid = str(f.get("item_id", ""))
        if "window" in iid or "door" in iid:
            continue
        if any(f.get(k) is None for k in ("cx", "cy", "w", "h")):
            continue
        hw, hh = float(f["w"]) / 2, float(f["h"]) / 2
        r = float(f.get("rotation", 0) or 0) * _DEG
        cos, sin = math.cos(r), math.sin(r)
        ox, oz = (float(f["cx"]) - cx) * mpp, (float(f["cy"]) - cy) * mpp
        for dx, dy in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)):
            pts.append((ox + (dx * cos - dy * sin) * mpp, oz + (dx * sin + dy * cos) * mpp))
    return pts


def solve_ai_camera(
    furniture_pts: list[tuple[float, float]], fit_dist: float, fov: float, aspect: float
) -> dict[str, Any]:
    """Faithful port of frontend solveAiCamera (dollhouse 3/4). windows omitted (they only
    break ties among equally-covering corners); coverage dominates. Deterministic."""
    corners = [(1, 1), (1, -1), (-1, 1), (-1, -1)]
    n = len(furniture_pts)
    cxm = sum(p[0] for p in furniture_pts) / n if n else 0.0
    czm = sum(p[1] for p in furniture_pts) / n if n else 0.0
    target = (cxm, 0.5, czm)
    norm = math.hypot(0.55, 0.72, 0.95)
    h_half = math.atan(math.tan((fov / 2) * _DEG) * aspect)

    def evaluate(c: tuple[int, int]) -> dict[str, Any]:
        pos = ((0.55 * c[0] / norm) * fit_dist, (0.72 / norm) * fit_dist, (0.95 * c[1] / norm) * fit_dist)
        vx, vz = target[0] - pos[0], target[2] - pos[2]
        vlen = math.hypot(vx, vz) or 1.0
        visible = 0
        for px, pz in furniture_pts:
            dx, dz = px - pos[0], pz - pos[2]
            dl = math.hypot(dx, dz) or 1.0
            cos = (vx * dx + vz * dz) / (vlen * dl)
            if math.acos(max(-1.0, min(1.0, cos))) <= h_half:
                visible += 1
        coverage = visible / n if n else 1.0
        return {"pos": pos, "visible": visible, "score": coverage * 5.0}

    best = evaluate(corners[0])
    for c in corners[1:]:
        e = evaluate(c)
        if e["score"] > best["score"]:
            best = e
    return {"position": best["pos"], "target": target,
            "visible": best["visible"], "total": n, "fov": fov, "aspect": aspect}


def _fit_dist(furniture: list[dict[str, Any]], cx: float, cy: float, mpp: float,
              bbox: tuple[float, float, float, float]) -> float:
    """Ported aiFitDist: radius of furniture+room extents, backed off for AI_FOV + 40% margin."""
    half_x = bbox[2] * mpp / 2
    half_z = bbox[3] * mpp / 2
    for f in furniture:
        if any(f.get(k) is None for k in ("cx", "cy", "w", "h")):
            continue
        fx = abs((float(f["cx"]) - cx) * mpp)
        fz = abs((float(f["cy"]) - cy) * mpp)
        reach = (max(float(f["w"]), float(f["h"])) * mpp) / 2
        half_x = max(half_x, fx + reach)
        half_z = max(half_z, fz + reach)
    radius = math.hypot(half_x, half_z)
    return (radius / math.tan((AI_FOV / 2) * _DEG)) * 1.4


def _project(p: Vec3, eye: Vec3, basis: tuple[Vec3, Vec3, Vec3], f_persp: float,
             aspect: float, w: int, h: int, near: float = 0.05) -> tuple[float, float] | None:
    """World point → screen pixel via a Three.js-style perspective camera, or None if behind."""
    xa, ya, za = basis
    d = _sub(p, eye)
    cz = _dot(d, za)
    if cz >= -near:           # behind the near plane (camera looks down -Z)
        return None
    cx_ = _dot(d, xa)
    cy_ = _dot(d, ya)
    ndc_x = (f_persp / aspect) * cx_ / (-cz)
    ndc_y = f_persp * cy_ / (-cz)
    return ((ndc_x * 0.5 + 0.5) * w, (0.5 - ndc_y * 0.5) * h)


def _item_height_m(item_id: str | None) -> float:
    info = CLASS_BY_ITEM_ID.get(item_id or "")
    return (info.height_mm / 1000.0) if info else _DEFAULT_FURN_HEIGHT_M


def render_structural_pass(
    scene: dict[str, Any],
    room: dict[str, Any],
    *,
    width: int = BASE_CAPTURE_W,
    height: int = BASE_CAPTURE_H,
    mpp: float | None = None,
) -> tuple[bytes, dict[str, Any]]:
    """Render a perspective structural edge map (PNG) for ONE room + provenance.

    Reuses canonical geometry only: room boundary (→ wall edges) and furniture (→ 3D box
    edges), projected through the ported dollhouse camera. Deterministic; canonical data is
    never mutated.
    """
    rooms = scene.get("rooms", []) or []
    mpp = compute_mpp(rooms) if mpp is None else mpp
    bbox = tuple(float(v) for v in room["bbox"])  # [x, y, w, h] world px
    cx, cy = bbox[0] + bbox[2] / 2, bbox[1] + bbox[3] / 2
    furniture = [f for f in (room.get("furniture", []) or [])
                 if not (str(f.get("item_id", "")).startswith("room-tag"))]

    fpts = _furniture_points(furniture, cx, cy, mpp)
    fit = _fit_dist(furniture, cx, cy, mpp, bbox)
    cam = solve_ai_camera(fpts, fit, AI_FOV, width / height)
    eye: Vec3 = tuple(cam["position"])  # type: ignore[assignment]
    target: Vec3 = tuple(cam["target"])  # type: ignore[assignment]
    up: Vec3 = (0.0, 1.0, 0.0)
    za = _norm(_sub(eye, target))
    xa = _norm(_cross(up, za))
    ya = _cross(za, xa)
    f_persp = 1.0 / math.tan((AI_FOV / 2) * _DEG)

    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    def seg(p1: Vec3, p2: Vec3, color: tuple[int, int, int], wdt: int) -> bool:
        a = _project(p1, eye, (xa, ya, za), f_persp, width / height, width, height)
        b = _project(p2, eye, (xa, ya, za), f_persp, width / height, width, height)
        if a is None or b is None:
            return False
        draw.line([a[0], a[1], b[0], b[1]], fill=color, width=wdt)
        return True

    # Walls from the room boundary (preferred) or the bbox rectangle, as vertical quads.
    boundary = room.get("boundary")
    if boundary and len(boundary) >= 3:
        ring = [((float(px) - cx) * mpp, (float(py) - cy) * mpp) for px, py in boundary]
    else:
        x0, y0, bw, bh = bbox
        ring = [((x0 - cx) * mpp, (y0 - cy) * mpp), ((x0 + bw - cx) * mpp, (y0 - cy) * mpp),
                ((x0 + bw - cx) * mpp, (y0 + bh - cy) * mpp), ((x0 - cx) * mpp, (y0 + bh - cy) * mpp)]
    walls_drawn = 0
    for i in range(len(ring)):
        x1, z1 = ring[i]
        x2, z2 = ring[(i + 1) % len(ring)]
        drew = False
        drew |= seg((x1, 0.0, z1), (x2, 0.0, z2), (70, 70, 70), 2)          # base
        drew |= seg((x1, _WALL_HEIGHT_M, z1), (x2, _WALL_HEIGHT_M, z2), (70, 70, 70), 2)  # top
        drew |= seg((x1, 0.0, z1), (x1, _WALL_HEIGHT_M, z1), (70, 70, 70), 2)            # vertical
        if drew:
            walls_drawn += 1

    # Furniture as 3D box wireframes.
    furn_drawn = 0
    for f in furniture:
        iid = str(f.get("item_id", ""))
        if "window" in iid or "door" in iid:
            continue
        if any(f.get(k) is None for k in ("cx", "cy", "w", "h")):
            continue
        hw, hh = float(f["w"]) / 2, float(f["h"]) / 2
        r = float(f.get("rotation", 0) or 0) * _DEG
        cos, sin = math.cos(r), math.sin(r)
        ox, oz = (float(f["cx"]) - cx) * mpp, (float(f["cy"]) - cy) * mpp
        hgt = _item_height_m(f.get("item_id"))
        base = [(ox + (dx * cos - dy * sin) * mpp, oz + (dx * sin + dy * cos) * mpp)
                for dx, dy in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh))]
        drew = False
        for i in range(4):
            x1, z1 = base[i]
            x2, z2 = base[(i + 1) % 4]
            drew |= seg((x1, 0.0, z1), (x2, 0.0, z2), (90, 60, 40), 2)                 # bottom
            drew |= seg((x1, hgt, z1), (x2, hgt, z2), (90, 60, 40), 2)                 # top
            drew |= seg((x1, 0.0, z1), (x1, hgt, z1), (90, 60, 40), 2)                 # vertical
        if drew:
            furn_drawn += 1

    buf = BytesIO()
    img.save(buf, format="PNG")
    provenance = {
        "coordinate_frame": "perspective_structural_v1",
        "camera_position": [round(v, 3) for v in eye],
        "camera_target": [round(v, 3) for v in target],
        "fov_deg": AI_FOV,
        "aspect": round(width / height, 4),
        "mpp": round(mpp, 6),
        "width": width,
        "height": height,
        "walls_drawn": walls_drawn,
        "furniture_total": len(furniture),
        "furniture_drawn": furn_drawn,
        "visible_furniture_points": cam["visible"],
        "note": "PROTOTYPE conditioning artifact — NOT wired to the live fal request; "
                "pixel-exact base-render alignment not guaranteed.",
    }
    return buf.getvalue(), provenance
