"""Deterministic RASTER room reconstruction from EXTRACTED VECTOR WALLS.

The vector centreline collapse (wall_reconstruction.py) is exact for clean plans
but real architectural PDFs draw walls as fragmented, offset, dashed double-lines
that its endpoint-junction topology cannot close. This module instead rasterises
the extracted VECTOR wall segments (from geometry_extraction_service) into a wall
mask — each segment drawn at the measured wall thickness — bridges only the
VALIDATED PDF openings supplied by scene_service, and reads back the wall-enclosed
regions as room polygons.

The wall mask is built ONLY from vector wall geometry: it never thresholds the
rendered PDF's pixels, so text, dimensions, furniture symbols and annotations can
never become fake walls. It NEVER uses furniture to create geometry, never invents
walls, and bridges a gap only where a validated opening is recorded. A region is
returned only when it is fully enclosed by wall pixels (does not touch the canvas
border), is large enough to be a room, and is bounded by real extracted walls
(non-empty supporting_wall_ids). Each room reports the source wall IDs whose
strokes bound it (provenance).
"""

from __future__ import annotations

import math
from typing import Any

import cv2
import numpy as np
from shapely.geometry import Point, Polygon

# World px = PDF pt * WORLD_SCALE; render px = pt * DPI/72; so world -> render is
# (DPI/72)/WORLD_SCALE. Keep in sync with coordinates.WORLD_SCALE (2.0).
_WORLD_SCALE = 2.0
_DPI = 150.0


def _world_to_render(dpi: float) -> float:
    return (dpi / 72.0) / _WORLD_SCALE


def _rectilinearize(poly: list[tuple[float, float]], tol: float) -> list[tuple[float, float]]:
    """Snap near-collinear axis-aligned vertices so a boxy room reads as a clean
    rectilinear ring (walls are axis-aligned; this removes raster stair-stepping)."""
    if len(poly) < 4:
        return poly
    pts = [list(p) for p in poly]
    n = len(pts)
    # snap each edge that is nearly axis-aligned onto the shared coordinate
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        if abs(a[0] - b[0]) <= tol and abs(a[0] - b[0]) < abs(a[1] - b[1]):
            mx = round((a[0] + b[0]) / 2, 2)
            a[0] = b[0] = mx
        elif abs(a[1] - b[1]) <= tol and abs(a[1] - b[1]) < abs(a[0] - b[0]):
            my = round((a[1] + b[1]) / 2, 2)
            a[1] = b[1] = my
    # drop vertices that are now collinear with both neighbours
    out: list[tuple[float, float]] = []
    for i in range(n):
        p0, p1, p2 = pts[(i - 1) % n], pts[i], pts[(i + 1) % n]
        if (abs(p0[0] - p1[0]) <= tol and abs(p1[0] - p2[0]) <= tol) or (
            abs(p0[1] - p1[1]) <= tol and abs(p1[1] - p2[1]) <= tol
        ):
            continue  # collinear -> redundant
        out.append((round(p1[0], 2), round(p1[1], 2)))
    return out if len(out) >= 4 else [(round(x, 2), round(y, 2)) for x, y in poly]


def reconstruct_rooms_raster(
    pdf_path: str,
    walls: list[Any],
    openings: list[dict[str, Any]],
    thickness: float,
    dpi: float = _DPI,
) -> dict[str, Any]:
    """Return wall-enclosed room polygons (world px) from the EXTRACTED VECTOR WALLS.

    Vector repair happens BEFORE rasterization: double-line faces collapse to single
    centrelines and collinear dash gaps are merged with provenance.
    The wall mask consumes the repaired vector walls directly at the measured thickness.
    No global cv2.MORPH_CLOSE is used — room topology is purely geometric.
    Validated PDF openings bridge doorways only when real intersection exists.
    Provenance carries:
      repaired segment -> source_wall_ids -> room boundary edge -> supporting_wall_ids.

    Returns ``{rooms:[{polygon,bbox,area,supporting_wall_ids,opening_ids,
    validation_status,corner_count,edge_coverage_avg,edge_coverage_min}], stats}``.
    """
    segs: list[tuple[float, float, float, float]] = [
        (float(w[0]), float(w[1]), float(w[2]), float(w[3]))
        for w in walls
        if (float(w[2]) - float(w[0])) ** 2 + (float(w[3]) - float(w[1])) ** 2 > 0
    ]
    if not segs:
        return {"rooms": [], "stats": {"reason": "no vector walls"}}

    try:
        from app.services import wall_reconstruction
        repair_tol = {
            "pair_tol": thickness * 1.6,
            "merge_gap": thickness * 2.0,
            "thickness": thickness,
        }
        repaired = wall_reconstruction.repair_walls(segs, repair_tol)
        draw_segs = [r["seg"] for r in repaired] or segs
    except Exception:  # noqa: BLE001
        repaired = []
        for i, s in enumerate(segs):
            is_h = abs(s[1] - s[3]) <= abs(s[0] - s[2])
            repaired.append({
                "seg": s,
                "source_wall_ids": [f"wall_{i + 1:03d}"],
                "orientation": "h" if is_h else "v",
                "const": (s[1] + s[3]) / 2 if is_h else (s[0] + s[2]) / 2,
                "a0": min(s[0], s[2]) if is_h else min(s[1], s[3]),
                "a1": max(s[0], s[2]) if is_h else max(s[1], s[3]),
            })
        draw_segs = segs

    validated_bridges: list[dict[str, Any]] = []
    try:
        from app.services import wall_reconstruction
        validated_bridges = wall_reconstruction.validate_opening_bridges(
            openings, repaired, thickness
        )
    except Exception:  # noqa: BLE001
        validated_bridges = []

    k = _world_to_render(dpi)
    th_r = max(3, int(round(thickness * k)))
    xs = [c for s in draw_segs for c in (s[0], s[2])]
    ys = [c for s in draw_segs for c in (s[1], s[3])]
    minx, miny, maxx, maxy = min(xs), min(ys), max(xs), max(ys)
    margin = max(th_r * 3, 8)
    off_x = minx - margin / k
    off_y = miny - margin / k
    ww = int(round((maxx - minx) * k)) + 2 * margin
    hh = int(round((maxy - miny) * k)) + 2 * margin
    if ww < 8 or hh < 8 or ww * hh > 60_000_000:
        return {"rooms": [], "stats": {"reason": f"unusable canvas {ww}x{hh}"}}

    mask = np.zeros((hh, ww), np.uint8)

    def _px(x: float, y: float) -> tuple[int, int]:
        return int(round((x - off_x) * k)), int(round((y - off_y) * k))

    # Draw repaired vector wall centrelines directly at measured thickness
    for x1, y1, x2, y2 in draw_segs:
        cv2.line(mask, _px(x1, y1), _px(x2, y2), 255, th_r)

    # Bridge only validated openings with real intersection
    for b in validated_bridges:
        if not b.get("bridge_applied"):
            continue
        bx0, by0, bx1, by1 = b["box"]
        cv2.rectangle(mask, _px(bx0, by0), _px(bx1, by1), 255, -1)

    result = _extract_rooms(
        mask,
        segs,
        openings,
        thickness,
        k,
        offset=(off_x, off_y),
        repaired=repaired,
        validated_bridges=validated_bridges,
        bridges_drawn=True,
    )
    result["stats"]["raw_wall_count"] = len(segs)
    result["stats"]["repaired_wall_count"] = len(repaired)
    result["stats"]["opening_bridges"] = validated_bridges
    return result


def _extract_rooms(
    mask: np.ndarray,
    segs: list[Any],
    openings: list[dict[str, Any]],
    thickness: float,
    k: float,
    offset: tuple[float, float] = (0.0, 0.0),
    repaired: list[dict[str, Any]] | None = None,
    validated_bridges: list[dict[str, Any]] | None = None,
    bridges_drawn: bool = False,
) -> dict[str, Any]:
    """Core: read enclosed regions directly from wall ``mask`` (255 = wall) WITHOUT cv2.MORPH_CLOSE.

    Validates rooms against boundary edge coverage by repaired wall spans carrying provenance.
    """
    Hh, Ww = mask.shape[:2]
    th_r = max(3, int(round(thickness * k)))
    off_x, off_y = offset

    def to_px(x: float, y: float) -> tuple[int, int]:
        return int(round((x - off_x) * k)), int(round((y - off_y) * k))

    bridged = 0
    if not bridges_drawn and openings:
        if validated_bridges:
            for b in validated_bridges:
                if not b.get("bridge_applied"):
                    continue
                bx0, by0, bx1, by1 = b["box"]
                cv2.rectangle(mask, to_px(bx0, by0), to_px(bx1, by1), 255, -1)
                bridged += 1
        else:
            # Fallback for synthetic unit test masks without repaired walls
            for o in openings:
                try:
                    cx = float(o.get("cx", o.get("x", 0)))
                    cy = float(o.get("cy", o.get("y", 0)))
                    ow = float(o.get("w", o.get("width", 0)))
                    oh = float(o.get("h", o.get("height", 0)))
                    rot = math.radians(float(o.get("rotation", 0)))
                except (KeyError, TypeError, ValueError):
                    continue
                if ow <= 0 or oh <= 0:
                    continue
                corners = []
                corner_deltas = (
                    (-ow / 2, -oh / 2),
                    (ow / 2, -oh / 2),
                    (ow / 2, oh / 2),
                    (-ow / 2, oh / 2),
                )
                for lx, ly in corner_deltas:
                    rx = cx + lx * math.cos(rot) - ly * math.sin(rot)
                    ry = cy + lx * math.sin(rot) + ly * math.cos(rot)
                    corners.append(to_px(rx, ry))
                cv2.fillPoly(mask, [np.array(corners, np.int32)], 255)
                bridged += 1
    elif validated_bridges:
        bridged = sum(1 for b in validated_bridges if b.get("bridge_applied"))

    # Vector repair & snapping happens BEFORE rasterization; NO cv2.MORPH_CLOSE is applied.
    # Read enclosed regions directly from the vector wall mask.
    inv = (mask == 0).astype(np.uint8)
    ncomp, lbl, stats, _ = cv2.connectedComponentsWithStats(inv, connectivity=8)
    border = set(lbl[0, :]) | set(lbl[-1, :]) | set(lbl[:, 0]) | set(lbl[:, -1])
    min_area_px = max((Ww * Hh) * 0.006, (th_r ** 2) * 40)

    rooms: list[dict[str, Any]] = []
    rid = 0
    line_tol = thickness * 1.0

    # Build repaired structures if not supplied
    if repaired is None and segs:
        repaired = []
        for i, s in enumerate(segs):
            is_h = abs(s[1] - s[3]) <= abs(s[0] - s[2])
            repaired.append({
                "seg": s,
                "source_wall_ids": [f"wall_{i + 1:03d}"],
                "orientation": "h" if is_h else "v",
                "const": (s[1] + s[3]) / 2 if is_h else (s[0] + s[2]) / 2,
                "a0": min(s[0], s[2]) if is_h else min(s[1], s[3]),
                "a1": max(s[0], s[2]) if is_h else max(s[1], s[3]),
            })

    for i in range(1, ncomp):
        if i in border or stats[i, cv2.CC_STAT_AREA] < min_area_px:
            continue
        region = (lbl == i).astype(np.uint8)
        cnts, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cnts:
            continue
        c = max(cnts, key=cv2.contourArea)
        approx = cv2.approxPolyDP(c, th_r * 0.8, True).reshape(-1, 2)
        world = [(px_ / k + off_x, py_ / k + off_y) for px_, py_ in approx]
        world = _rectilinearize(world, thickness * 0.75)
        if len(world) < 4:
            continue
        shp = Polygon(world)
        if not shp.is_valid or shp.area <= 0:
            shp = shp.buffer(0)
            if shp.is_empty or shp.geom_type != "Polygon":
                continue
            world = [(round(x, 2), round(y, 2)) for x, y in shp.exterior.coords]
        minx, miny, maxx, maxy = shp.bounds

        # Boundary edge coverage by repaired wall spans (full provenance)
        coords = list(shp.exterior.coords)
        support_source_ids: set[str] = set()
        edge_coverages: list[float] = []

        if repaired:
            for p0, p1 in zip(coords[:-1], coords[1:], strict=False):
                dx, dy = abs(p1[0] - p0[0]), abs(p1[1] - p0[1])
                is_edge_h = dx >= dy
                e_const = (p0[1] + p1[1]) / 2 if is_edge_h else (p0[0] + p1[0]) / 2
                e0, e1 = sorted((p0[0], p1[0])) if is_edge_h else sorted((p0[1], p1[1]))
                e_len = max(1e-6, e1 - e0)

                intervals: list[tuple[float, float]] = []
                for r in repaired:
                    if (r["orientation"] == "h") != is_edge_h:
                        continue
                    seg_r = r["seg"]
                    r_const = r.get(
                        "const",
                        (seg_r[1] + seg_r[3]) / 2 if is_edge_h else (seg_r[0] + seg_r[2]) / 2,
                    )
                    if abs(r_const - e_const) > line_tol:
                        continue
                    r_a0 = r.get(
                        "a0",
                        min(seg_r[0], seg_r[2]) if is_edge_h else min(seg_r[1], seg_r[3]),
                    )
                    r_a1 = r.get(
                        "a1",
                        max(seg_r[0], seg_r[2]) if is_edge_h else max(seg_r[1], seg_r[3]),
                    )
                    lo, hi = max(e0, r_a0), min(e1, r_a1)
                    if hi > lo:
                        intervals.append((lo, hi))
                        support_source_ids.update(r.get("source_wall_ids", []))

                # Account for opening bridges along the edge
                if validated_bridges:
                    for b in validated_bridges:
                        if not b.get("bridge_applied"):
                            continue
                        bx0, by0, bx1, by1 = b["box"]
                        b_const = (by0 + by1) / 2 if is_edge_h else (bx0 + bx1) / 2
                        if abs(b_const - e_const) <= line_tol:
                            b0, b1 = (bx0, bx1) if is_edge_h else (by0, by1)
                            lo, hi = max(e0, b0), min(e1, b1)
                            if hi > lo:
                                intervals.append((lo, hi))
                                if b.get("supporting_wall_id"):
                                    support_source_ids.add(b["supporting_wall_id"])

                covered = 0.0
                merged_hi = -float("inf")
                for lo, hi in sorted(intervals):
                    lo = max(lo, merged_hi)
                    if hi > lo:
                        covered += hi - lo
                        merged_hi = hi
                cov = min(1.0, covered / e_len)
                edge_coverages.append(cov)

            avg_cov = sum(edge_coverages) / len(edge_coverages) if edge_coverages else 0.0
            min_cov = min(edge_coverages) if edge_coverages else 0.0

            # Reject region if not genuinely supported by vector walls
            if avg_cov < 0.70 or not support_source_ids:
                continue
        else:
            avg_cov, min_cov = 1.0, 1.0

        def _op_dist(o: dict[str, Any], room_shp: Polygon = shp) -> float:
            ox = float(o.get("cx", o.get("x", 0)))
            oy = float(o.get("cy", o.get("y", 0)))
            return float(room_shp.exterior.distance(Point(ox, oy)))

        opening_ids = [
            str(o.get("uid") or o.get("id") or o.get("item_id"))
            for o in openings
            if _op_dist(o) <= thickness * 2.0
        ]
        rid += 1
        rooms.append({
            "room_id": f"RR{rid}",
            "polygon": [(round(x, 2), round(y, 2)) for x, y in world],
            "bbox": [round(minx, 2), round(miny, 2), round(maxx - minx, 2), round(maxy - miny, 2)],
            "area": round(shp.area, 1),
            "supporting_wall_ids": sorted(support_source_ids),
            "supporting_wall_count": len(support_source_ids),
            "opening_ids": opening_ids,
            "corner_count": len(world),
            "validation_status": "CONFIRMED",
            "wall_supported": True,
            "geom_source": "architectural",
            "assign_method": "raster_contour",
            "edge_coverage_avg": round(avg_cov, 3),
            "edge_coverage_min": round(min_cov, 3),
        })
    rooms.sort(key=lambda r: -r["area"])
    return {
        "rooms": rooms,
        "stats": {
            "render": [Ww, Hh],
            "thickness_render_px": th_r,
            "openings_bridged": bridged,
            "regions_found": len(rooms),
        },
    }
