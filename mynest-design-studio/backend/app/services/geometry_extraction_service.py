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

# Must match the frontend pdf.js viewport scale in loadPlanImage.ts.
WORLD_SCALE = 2.0

_AXIS_TOL = 0.9  # pts: a segment is axis-aligned if it deviates less than this
_MIN_WALL_LEN = 18.0  # pts: ignore very short segments (dimension ticks, marks)
_FRAME_EDGE_TOL = 3.0  # pts: drop lines lying on the drawing-sheet border


class GeometryError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _find_frame(
    rects: list[tuple[float, float, float, float]], page_area: float
) -> tuple[float, float, float, float] | None:
    """The drawing-sheet border: the largest rect that is not the whole page."""
    inner = [r for r in rects if (r[2] - r[0]) * (r[3] - r[1]) < 0.95 * page_area]
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
        lines = [
            (ln["x0"], ln["top"], ln["x1"], ln["bottom"], ln.get("stroking_color"))
            for ln in page.lines
        ]
        rects = [(r["x0"], r["top"], r["x1"], r["bottom"]) for r in page.rects]

    frame = _find_frame(rects, pw * ph)
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
    for x0, y0, x1, y1, color in lines:
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
        walls.append([x0 * scale, y0 * scale, x1 * scale, y1 * scale])
        wall_colors.append(hexc)

    return {
        "page": {"width": pw * scale, "height": ph * scale, "scale": scale},
        "walls": walls,
        "wall_colors": wall_colors,
    }


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
