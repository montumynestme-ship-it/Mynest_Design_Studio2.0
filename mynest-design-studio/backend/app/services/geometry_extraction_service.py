"""Deterministic floor-plan geometry extraction (Phase A).

Parses the *vector* geometry out of a plan PDF — walls come out as real line
segments, not guessed from pixels — and renders a deterministic **control image**
(walls + furniture footprints) that downstream ControlNet img2img will repaint
photorealistically WITHOUT moving any wall or furniture (see CLAUDE.md RULE #1).

Coordinate spaces
-----------------
- PDF points: pdfplumber's native units, top-left origin, y down.
- World px: the space furniture is stored in (``canonical_json`` cx/cy/w/h). The
  frontend rasterizes the PDF at ``scale = 2`` (``loadPlanImage.ts``), so
  ``world_px = pdf_pt * WORLD_SCALE``. Everything returned here is world px.
"""

import math
from io import BytesIO
from typing import Any

import pdfplumber
from PIL import Image, ImageDraw
from shapely.geometry import LineString, box

# Must match the frontend pdf.js viewport scale in loadPlanImage.ts.
WORLD_SCALE = 2.0

_AXIS_TOL = 0.9  # pts: a segment is axis-aligned if it deviates less than this
# Keep legitimate SHORT structural segments (wall jambs, corner caps, curve
# sub-segments). Only sub-pixel ticks are noise. The old 18pt floor silently
# dropped real jamb walls that room polygons need at their corners.
_MIN_WALL_LEN = 3.0  # pts
_FRAME_EDGE_TOL = 3.0  # pts: drop lines lying on the drawing-sheet border
# Source colours: structural walls are near-black; drafter layers colour-code
# door leaves (gold) and window glazing (cyan) — those are OPENINGS, not walls.
_DOOR_HEXES = ("#9e7700",)
_WINDOW_HEXES = ("#00ffff",)


class GeometryError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _find_frame(
    rects: list[tuple[float, float, float, float]], page_area: float
) -> tuple[float, float, float, float] | None:
    """The drawing-sheet border: the largest rect that is between 30% and 95% of page area."""
    inner = [
        r
        for r in rects
        if 0.30 * page_area < (r[2] - r[0]) * (r[3] - r[1]) < 0.95 * page_area
    ]
    if not inner:
        return None
    return max(inner, key=lambda r: (r[2] - r[0]) * (r[3] - r[1]))



def _stroke_hex(color: Any) -> str:
    """Normalise a pdfplumber stroking colour to a hex string. Near-black /
    grayscale-black collapses to the wall colour; anything distinctly coloured
    (e.g. windows drawn on their own layer) keeps its real colour so it can be
    rendered differently downstream."""
    wall = "#141414"
    try:
        if color is None:
            return wall
        if isinstance(color, int | float):
            v = int(round(float(color) * 255)) if float(color) <= 1 else int(color)
            r = g = b = max(0, min(255, v))
        elif isinstance(color, list | tuple):
            if len(color) == 1:
                v = int(round(float(color[0]) * 255))
                r = g = b = max(0, min(255, v))
            elif len(color) >= 3:
                r, g, b = (max(0, min(255, int(round(float(c) * 255)))) for c in color[:3])
            else:
                return wall
        else:
            return wall
    except (TypeError, ValueError):
        return wall
    # Near-black or near-grey → treat as a structural wall (uniform dark).
    if max(r, g, b) < 70 and (max(r, g, b) - min(r, g, b)) < 25:
        return wall
    return f"#{r:02x}{g:02x}{b:02x}"


def _is_annotation_color(hexc: str) -> bool:
    """Strong red is a drafter annotation / dimension / markup layer — not an
    architectural element — so it is dropped from the plan geometry."""
    if not (hexc.startswith("#") and len(hexc) == 7):
        return False
    r = int(hexc[1:3], 16)
    g = int(hexc[3:5], 16)
    b = int(hexc[5:7], 16)
    return r > 170 and g < 90 and b < 90


def extract_walls(pdf_path: str, scale: float = WORLD_SCALE) -> dict[str, Any]:
    """Return {'page': {w,h,scale}, 'walls': [...], 'wall_colors': [...]} in world px.

    ``wall_colors[i]`` is the source colour of ``walls[i]`` — structural walls are
    ``#141414``; lines the drafter colour-coded (windows/features) keep their hue.
    """
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        pw, ph = float(page.width), float(page.height)
        # Use page.EDGES, not page.lines: pdfplumber materialises the axis-aligned
        # segments of EVERY primitive (straight lines, rectangle sides AND the
        # straight sub-segments of path/curve objects). Real plans draw many walls
        # as path/curve primitives, so a line-only reader silently loses them.
        edges = [
            (e["x0"], e["top"], e["x1"], e["bottom"], e.get("stroking_color"),
             str(e.get("object_type", "edge")))
            for e in page.edges
            if e.get("orientation") in ("h", "v")
        ]
        rects = [
            (r["x0"], r["top"], r["x1"], r["bottom"], _stroke_hex(r.get("stroking_color")))
            for r in page.rects
        ]

    frame = _find_frame([r[:4] for r in rects], pw * ph)
    fx0, fy0, fx1, fy1 = frame if frame else (0.0, 0.0, pw, ph)

    def on_frame(cx: float, cy: float) -> bool:
        return (
            abs(cx - fx0) < _FRAME_EDGE_TOL
            or abs(cx - fx1) < _FRAME_EDGE_TOL
            or abs(cy - fy0) < _FRAME_EDGE_TOL
            or abs(cy - fy1) < _FRAME_EDGE_TOL
        )

    walls: list[list[float]] = []
    wall_colors: list[str] = []
    wall_sources: list[str] = []
    for x0, y0, x1, y1, color, otype in edges:
        is_v = abs(x1 - x0) < _AXIS_TOL
        is_h = abs(y1 - y0) < _AXIS_TOL
        if not (is_v or is_h):
            continue
        if math.hypot(x1 - x0, y1 - y0) < _MIN_WALL_LEN:
            continue
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if not (fx0 <= cx <= fx1 and fy0 <= cy <= fy1):
            continue  # outside the drawing (title block, legend, margins)
        if on_frame(cx, cy):
            continue  # the sheet border itself is not a wall
        hexc = _stroke_hex(color)
        if _is_annotation_color(hexc):
            continue  # red markup / dimension layer — not architecture
        # Door leaves (gold) and window glazing (cyan) are OPENINGS, not walls —
        # captured separately below so they are never treated as solid partitions.
        if hexc in _DOOR_HEXES or hexc in _WINDOW_HEXES:
            continue
        walls.append([x0 * scale, y0 * scale, x1 * scale, y1 * scale])
        wall_colors.append(hexc)
        wall_sources.append(otype)

    structured_walls: list[dict[str, Any]] = []
    for idx, (w, c, src) in enumerate(zip(walls, wall_colors, wall_sources, strict=False)):
        wx1, wy1, wx2, wy2 = w
        length = math.hypot(wx2 - wx1, wy2 - wy1)
        angle = math.degrees(math.atan2(wy2 - wy1, wx2 - wx1)) % 360.0
        structured_walls.append(
            {
                "id": f"wall_{idx + 1:03d}",
                "x1": round(wx1, 2),
                "y1": round(wy1, 2),
                "x2": round(wx2, 2),
                "y2": round(wy2, 2),
                "length": round(length, 2),
                "angle_deg": round(angle, 2),
                "thickness": 10.0,
                "height": 2.7,
                "color": c,
                "source": src,  # provenance: which PDF primitive this wall came from
            }
        )

    # Measured wall thickness (world px) — the footprint-crossing test needs it so
    # an opening drawn in the GAP of a double-line wall (its nearest stroke offset by
    # ~thickness) still reads as crossing that wall.
    from app.services import wall_reconstruction
    wall_thickness = 0.0
    try:
        segs_for_tol = [tuple(map(float, w)) for w in walls
                        if math.hypot(w[2] - w[0], w[3] - w[1]) > 0]
        wall_thickness = float(wall_reconstruction.measure_tolerances(segs_for_tol).get(
            "thickness") or 0.0)
    except Exception:  # noqa: BLE001 — thickness is an optional refinement of the band
        wall_thickness = 0.0

    openings = _extract_openings(
        rects, structured_walls, scale, (fx0, fy0, fx1, fy1), wall_thickness
    )

    return {
        "page": {"width": pw * scale, "height": ph * scale, "scale": scale},
        "walls": walls,
        "wall_colors": wall_colors,
        "wall_sources": wall_sources,
        "structured_walls": structured_walls,
        "openings": openings,
    }


def _pt_seg_dist(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """Distance from point to a segment (all same coordinate system)."""
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def _extract_openings(
    rects: list[tuple[float, float, float, float, str]],
    structured_walls: list[dict[str, Any]],
    scale: float,
    frame: tuple[float, float, float, float],
    wall_thickness: float = 0.0,
) -> list[dict[str, Any]]:
    """Normalize PDF door (gold) / window (cyan) rects into ONE opening schema, in
    the SAME world coordinate system as walls (cx/cy — never x/y):

        {id, kind, cx, cy, w, h, rotation, supporting_wall_id, source,
         validation_status, wall_distance_px, uncertain, uncertain_reason}

    Each opening is linked to its nearest structural wall and given the wall's
    orientation as its rotation. ``validation_status`` is ``VALID`` only when the
    dimensions are numeric+positive AND a real wall sits within a measured
    tolerance of the centre; otherwise ``UNCERTAIN`` (no supporting wall) or
    ``INVALID`` (bad geometry). Non-VALID openings are kept for diagnostics but must
    never be bridged into room topology — never dropped and never fabricated.
    """
    fx0, fy0, fx1, fy1 = frame
    openings: list[dict[str, Any]] = []
    counts = {"door": 0, "window": 0}
    for rx0, ry0, rx1, ry1, rhex in rects:
        kind = "door" if rhex in _DOOR_HEXES else "window" if rhex in _WINDOW_HEXES else None
        if kind is None:
            continue
        cx, cy = (rx0 + rx1) / 2 * scale, (ry0 + ry1) / 2 * scale
        if not (fx0 * scale <= cx <= fx1 * scale and fy0 * scale <= cy <= fy1 * scale):
            continue
        w, h = abs(rx1 - rx0) * scale, abs(ry1 - ry0) * scale
        # Nearest structural wall (same world coords) → supporting_wall_id + rotation.
        best_id, best_dist, best_angle, best_seg = None, math.inf, None, None
        for sw in structured_walls:
            d = _pt_seg_dist(cx, cy, sw["x1"], sw["y1"], sw["x2"], sw["y2"])
            if d < best_dist:
                best_id, best_dist, best_angle = sw["id"], d, sw["angle_deg"]
                best_seg = (sw["x1"], sw["y1"], sw["x2"], sw["y2"])
        # Link only when a wall is within one opening-leaf of the centre; otherwise
        # the opening is uncertain (do not fabricate a wall association).
        link_tol = max(60.0, max(w, h) * 1.5)
        # Validate BEFORE use (goal §1/§2). An opening is VALID only when ALL hold:
        #   • finite, positive dimensions and a valid (finite) rotation,
        #   • a real supporting wall whose centre-distance is within link_tol,
        #   • the opening FOOTPRINT actually crosses that wall region — not merely
        #     sits near it (the wall stroke must pass within the opening's own depth
        #     of its footprint, so a box lying beside a wall is rejected).
        # Only VALID openings bridge room topology; UNCERTAIN/INVALID are kept for
        # diagnostics but never bridged or treated as architectural truth.
        dims_ok = all(math.isfinite(v) for v in (cx, cy, w, h)) and w > 0 and h > 0
        near_wall = best_id is not None and best_dist <= link_tol
        crosses_wall = False
        if dims_ok and near_wall and best_seg is not None:
            # Reach: the opening's own depth OR the measured wall thickness (a stroke
            # of a double-line wall sits ~thickness from the opening centre).
            band = max(min(w, h) * 0.75, wall_thickness, 6.0)
            foot = box(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
            wall_line = LineString([(best_seg[0], best_seg[1]), (best_seg[2], best_seg[3])])
            crosses_wall = wall_line.distance(foot) <= band
        if not dims_ok:
            status, reason = "INVALID", "non-finite or non-positive opening dimensions"
        elif not near_wall:
            status = "UNCERTAIN"
            reason = (f"no wall within {round(link_tol)}px of centre "
                      f"(nearest {round(best_dist, 1)}px)")
        elif not crosses_wall:
            status = "UNCERTAIN"
            reason = (f"footprint does not cross supporting wall {best_id} "
                      f"(centre near at {round(best_dist, 1)}px but box beside it)")
        else:
            status, reason = "VALID", None
        supported = status == "VALID"
        valid = supported
        if valid and best_angle is not None:
            rotation = 90.0 if 45.0 <= (best_angle % 180.0) < 135.0 else 0.0
        else:
            rotation = 0.0 if w >= h else 90.0  # fall back to the opening's own aspect
        counts[kind] += 1
        openings.append({
            "id": f"{kind}_{counts[kind]:03d}",
            "kind": kind,
            "cx": round(cx, 2),
            "cy": round(cy, 2),
            "w": round(w, 2),
            "h": round(h, 2),
            "rotation": rotation,
            "supporting_wall_id": best_id if valid else None,
            "source": "pdf_rect",
            "validation_status": status,
            "wall_distance_px": round(best_dist, 2) if math.isfinite(best_dist) else None,
            "uncertain": not valid,
            "uncertain_reason": reason,
        })
    return openings



def _rotated_rect(
    cx: float, cy: float, w: float, h: float, deg: float
) -> list[tuple[float, float]]:
    r = math.radians(deg)
    cos, sin = math.cos(r), math.sin(r)
    corners = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
    return [(cx + dx * cos - dy * sin, cy + dx * sin + dy * cos) for dx, dy in corners]


def render_control_image(geometry: dict[str, Any], furniture: list[dict[str, Any]]) -> bytes:
    """Deterministic base: black walls + labelled furniture footprints, world px.

    This is the authoritative geometry the AI must preserve. It is drawn purely
    from extracted walls and stored furniture coordinates — nothing is invented.
    """
    page = geometry["page"]
    img = Image.new("RGB", (int(page["width"]), int(page["height"])), "white")
    draw = ImageDraw.Draw(img)

    for x1, y1, x2, y2 in geometry["walls"]:
        draw.line([x1, y1, x2, y2], fill=(0, 0, 0), width=5)

    for f in furniture:
        cx, cy = float(f["cx"]), float(f["cy"])
        poly = _rotated_rect(cx, cy, float(f["w"]), float(f["h"]), float(f.get("rotation", 0)))
        draw.polygon(poly, fill=(225, 210, 195), outline=(90, 60, 40))
        draw.line([*poly, poly[0]], fill=(90, 60, 40), width=3)
        label = str(f["item_id"]).replace("-", " ")
        draw.text((cx - len(label) * 3, cy - 5), label, fill=(60, 40, 25))

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def render_canny_control(
    geometry: dict[str, Any], furniture: list[dict[str, Any]], max_side: int = 1408
) -> tuple[bytes, int, int]:
    """ControlNet-canny edge map: white walls + furniture outlines on black.

    Returns (png_bytes, width, height). Downscaled so the long side is <= max_side
    and both sides are multiples of 16 (flux ControlNet requirement). This is the
    geometry the AI is forced to trace in Phase C — nothing is filled or labelled
    so the edges stay clean.
    """
    page = geometry["page"]
    w_full, h_full = int(page["width"]), int(page["height"])
    img = Image.new("RGB", (w_full, h_full), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    for x1, y1, x2, y2 in geometry["walls"]:
        draw.line([x1, y1, x2, y2], fill=(255, 255, 255), width=6)
    for f in furniture:
        poly = _rotated_rect(
            float(f["cx"]),
            float(f["cy"]),
            float(f["w"]),
            float(f["h"]),
            float(f.get("rotation", 0)),
        )
        draw.line([*poly, poly[0]], fill=(255, 255, 255), width=4)

    scale = min(1.0, max_side / max(w_full, h_full))
    out_w = max(16, int(w_full * scale) // 16 * 16)
    out_h = max(16, int(h_full * scale) // 16 * 16)
    img = img.resize((out_w, out_h), Image.Resampling.LANCZOS)

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue(), out_w, out_h
