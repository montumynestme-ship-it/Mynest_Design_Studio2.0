"""Deterministic architectural SHAPE extraction (audit stage 3, reinforced).

Produces one cohesive, topology-complete architectural structure from wall
segments — enough to reconstruct the original floor-plan topology:

    {
      "coordinate_space": "source_pixels",
      "walls":     [{id, x1,y1,x2,y2, orientation, thickness, confidence,
                     source, source_wall_ids, evidence_fragments}],
      "junctions": [{id, type: "L"|"T"|"X", x, y, wall_ids}],
      "rooms":     [{id, polygon, supporting_wall_ids, corner_junction_ids, status}],
      "openings":  [{id, kind, cx,cy,w,h, supporting_wall_id, source_wall_ids,
                     status: "VALID"|"UNCERTAIN"|"INVALID", distance_px}],
      "tolerances": {...}, "stats": {...}
    }

It COMPOSES the existing deterministic engine (``wall_reconstruction``): fragmented
+ double-line segments are merged deterministically into centrelines with
provenance; T/L junctions and closed room boundaries come from the strict
point→perpendicular-segment topology (never fabricates a wall to close a room —
unproven rooms stay UNCERTAIN); openings are attached to their supporting wall span
whenever they lie on one, else marked UNCERTAIN. Shared walls stay a single span
(never duplicated or moved). Source pixel coordinates are preserved throughout.

Two entry points:
- ``extract_shapes(segments, openings, thickness)`` — from any wall SEGMENTS
  (vector PDF strokes OR CV-detected lines). Pure geometry, fully unit-testable.
- ``extract_shapes_from_image(pil_image, openings)`` — a deterministic OpenCV
  raster path (preprocess → edge → Hough → axis-snapped segments) for raster/scanned
  plans, then the same ``extract_shapes``. No FLUX, no text-to-image, no ML.
"""

from __future__ import annotations

import math
from typing import Any

from app.services import wall_reconstruction as wr

Seg = tuple[float, float, float, float]

_JTYPE = {"L_JUNCTION": "L", "T_JUNCTION": "T", "X_JUNCTION": "X"}


def _clean_segments(segments: list[Any]) -> list[Seg]:
    out: list[Seg] = []
    for s in segments:
        try:
            x1, y1, x2, y2 = (float(s[0]), float(s[1]), float(s[2]), float(s[3]))
        except (TypeError, ValueError, IndexError):
            continue
        if math.hypot(x2 - x1, y2 - y1) > 0:
            out.append((x1, y1, x2, y2))
    return out


def _wall_confidence(n_fragments: int, length: float, unit: float) -> float:
    """Deterministic confidence from source evidence: a span backed by more source
    fragments (double-line faces / merged dashes) and greater length is stronger."""
    ev = min(1.0, 0.55 + 0.15 * max(0, n_fragments - 1))
    length_factor = min(1.0, length / max(1.0, unit))
    return round(min(1.0, 0.5 * ev + 0.5 * (0.5 + 0.5 * length_factor)), 3)


def extract_shapes(
    segments: list[Any],
    openings: list[dict[str, Any]] | None = None,
    thickness: float | None = None,
    source: str = "vector",
) -> dict[str, Any]:
    """Compose merged walls + junctions + rooms + attached openings from raw wall
    segments. Deterministic; preserves source pixel coordinates; invents nothing."""
    segs = _clean_segments(segments)
    empty = {
        "coordinate_space": "source_pixels", "walls": [], "junctions": [],
        "rooms": [], "openings": [], "tolerances": {},
        "stats": {"raw_segments": 0, "walls": 0, "junctions": 0, "rooms_confirmed": 0,
                  "rooms_uncertain": 0, "openings": 0},
        "source": source,
    }
    if not segs:
        return empty

    tol = wr.measure_tolerances(segs)
    th = float(thickness) if thickness else float(tol.get("thickness") or 0.0)
    unit = float(tol.get("unit") or 1.0)

    # 1) Merge fragmented + double-line segments → centrelines (with provenance).
    repaired = wr.repair_walls(segs, {**tol, "thickness": th})
    walls: list[dict[str, Any]] = []
    hspans: list[tuple] = []
    vspans: list[tuple] = []
    counts = {"h": 0, "v": 0}
    for r in repaired:
        x1, y1, x2, y2 = r["seg"]
        src_ids = r.get("source_wall_ids", [])
        length = math.hypot(x2 - x1, y2 - y1)
        orient = r["orientation"]
        wall_id = f"{'H' if orient == 'h' else 'V'}{counts[orient]}"
        counts[orient] += 1
        walls.append({
            "id": wall_id,
            "x1": round(x1, 2), "y1": round(y1, 2), "x2": round(x2, 2), "y2": round(y2, 2),
            "orientation": r["orientation"],
            "thickness": round(th, 2),
            "confidence": _wall_confidence(len(src_ids), length, unit),
            "source": source,
            "source_wall_ids": src_ids,          # provenance to original strokes
            "evidence_fragments": len(src_ids),
        })
        span = (r["const"], r["a0"], r["a1"], set(src_ids))
        (hspans if r["orientation"] == "h" else vspans).append(span)

    # 2/3) Junctions + closed room boundaries from the strict topology engine.
    bridge = [o for o in (openings or []) if o.get("kind") in ("door", "window", "opening")]
    topo = wr.reconstruct_rooms_topology(segs, openings=bridge or None)

    junctions = [{
        "id": j["junction_id"],
        "type": _JTYPE.get(j["junction_type"], j["junction_type"]),
        "x": round(float(j["coordinate"][0]), 2),
        "y": round(float(j["coordinate"][1]), 2),
        "wall_ids": j.get("incident_wall_ids") or j.get("walls") or [],
    } for j in topo.get("junctions", [])]

    rooms: list[dict[str, Any]] = []
    for r in topo.get("rooms", []):
        rooms.append({
            "id": r.get("room_id") or f"room_{len(rooms)}",
            "polygon": r["polygon"],
            "supporting_wall_ids": r.get("supporting_wall_ids", []),
            "corner_junction_ids": r.get("corner_junction_ids", []),
            "status": "CONFIRMED",
        })
    for c in topo.get("all_candidates", []):
        if c.get("validation_status") == "CONFIRMED":
            continue
        rooms.append({
            "id": c.get("room_id") or f"cand_{len(rooms)}",
            "polygon": c.get("polygon", []),
            "supporting_wall_ids": c.get("supporting_wall_ids", []),
            "corner_junction_ids": c.get("corner_junction_ids", []),
            "status": "UNCERTAIN",
            "reasons": c.get("rejection_reasons", []),
        })

    # 4) Attach openings to their supporting wall span (else UNCERTAIN — unowned).
    out_openings: list[dict[str, Any]] = []
    for k, o in enumerate(openings or []):
        try:
            cx = float(o.get("cx", o.get("x")))
            cy = float(o.get("cy", o.get("y")))
            ow = float(o.get("w", o.get("width", 0)))
            oh = float(o.get("h", o.get("height", 0)))
        except (TypeError, ValueError):
            out_openings.append({"id": o.get("id") or f"op_{k}", "kind": o.get("kind", "opening"),
                                 "status": "INVALID", "supporting_wall_id": None,
                                 "source_wall_ids": [], "reason": "non-numeric geometry"})
            continue
        if ow <= 0 or oh <= 0 or not all(math.isfinite(v) for v in (cx, cy, ow, oh)):
            out_openings.append({"id": o.get("id") or f"op_{k}", "kind": o.get("kind", "opening"),
                                 "cx": cx, "cy": cy, "w": ow, "h": oh, "status": "INVALID",
                                 "supporting_wall_id": None, "source_wall_ids": [],
                                 "reason": "non-positive dimensions"})
            continue
        link = wr.opening_on_wall(o, hspans, vspans, th)
        out_openings.append({
            "id": o.get("id") or f"op_{k}",
            "kind": o.get("kind", "opening"),
            "cx": round(cx, 2), "cy": round(cy, 2), "w": round(ow, 2), "h": round(oh, 2),
            "supporting_wall_id": link["wall_id"],
            "source_wall_ids": link["source_ids"],
            "status": "VALID" if link["on_wall"] else "UNCERTAIN",
            "distance_px": link["distance"],
        })

    return {
        "coordinate_space": "source_pixels",
        "walls": walls,
        "junctions": junctions,
        "rooms": rooms,
        "openings": out_openings,
        "tolerances": {k: round(float(v), 2) for k, v in tol.items()},
        "source": source,
        "stats": {
            "raw_segments": len(segs),
            "walls": len(walls),
            "junctions": len(junctions),
            "junctions_L": sum(1 for j in junctions if j["type"] == "L"),
            "junctions_T": sum(1 for j in junctions if j["type"] == "T"),
            "rooms_confirmed": sum(1 for r in rooms if r["status"] == "CONFIRMED"),
            "rooms_uncertain": sum(1 for r in rooms if r["status"] == "UNCERTAIN"),
            "openings": len(out_openings),
            "openings_valid": sum(1 for o in out_openings if o["status"] == "VALID"),
            "openings_uncertain": sum(1 for o in out_openings if o["status"] == "UNCERTAIN"),
        },
    }


# ── Deterministic CV raster path (OpenCV; no ML, no generation) ──────────────

def detect_wall_segments(
    pil_image,
    dark_threshold: int = 128,
    hough_threshold: int = 60,
    min_line_frac: float = 0.02,
    max_gap_frac: float = 0.01,
    axis_tol_deg: float = 8.0,
) -> list[Seg]:
    """Detect axis-aligned wall line segments from a raster floor-plan image.

    Deterministic pipeline: greyscale → inverse binary threshold (walls are the dark
    linework) → Canny edges → probabilistic Hough transform → keep near-axis lines
    and snap them exactly to horizontal/vertical. Coordinates are SOURCE PIXELS.
    Diagonal/curved marks are dropped (not forced into walls). Requires OpenCV.
    """
    import cv2
    import numpy as np

    arr = np.array(pil_image.convert("L"))
    h, w = arr.shape[:2]
    _, binary = cv2.threshold(arr, dark_threshold, 255, cv2.THRESH_BINARY_INV)
    edges = cv2.Canny(binary, 50, 150, apertureSize=3)
    min_len = max(10, int(min(h, w) * min_line_frac))
    max_gap = max(3, int(min(h, w) * max_gap_frac))
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, hough_threshold,
                            minLineLength=min_len, maxLineGap=max_gap)
    if lines is None:
        return []
    segs: list[Seg] = []
    for ln in lines:
        flat = ln.reshape(-1)
        x1, y1, x2, y2 = float(flat[0]), float(flat[1]), float(flat[2]), float(flat[3])
        ang = abs(math.degrees(math.atan2(y2 - y1, x2 - x1))) % 180.0
        if ang <= axis_tol_deg or ang >= 180.0 - axis_tol_deg:      # horizontal
            yy = round((y1 + y2) / 2.0, 1)
            segs.append((min(x1, x2), yy, max(x1, x2), yy))
        elif abs(ang - 90.0) <= axis_tol_deg:                        # vertical
            xx = round((x1 + x2) / 2.0, 1)
            segs.append((xx, min(y1, y2), xx, max(y1, y2)))
        # else: diagonal — not a reliable axis-aligned wall; dropped
    return segs


def extract_shapes_from_image(
    pil_image,
    openings: list[dict[str, Any]] | None = None,
    **detect_kwargs: Any,
) -> dict[str, Any]:
    """Full raster stage 3: image → axis-aligned wall segments → architectural
    shapes. Source pixel coordinates preserved. No FLUX/ML/text-to-image."""
    segs = detect_wall_segments(pil_image, **detect_kwargs)
    return extract_shapes(segs, openings=openings, source="raster")
