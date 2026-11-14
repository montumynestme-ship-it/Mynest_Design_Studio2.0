"""Extraction diagnostic report (spec §13/§14/§24).

Composes the authoritative chain SOURCE floor plan -> canonical SceneRoom JSON ->
geometric reconstruction -> validation into ONE deterministic per-room report, so
a developer can see whether the *canonical is correct* BEFORE blaming the 3D base
or the AI render. It runs only the existing deterministic pipeline (walls from PDF
vectors, furniture from the saved canonical, rooms/doors/windows from
architectural_service) — it does NOT invent, ML-guess, or VLM-guess anything.

Per room it reports counts, every furniture item's exact transform, each window's
wall assignment, and hard validation flags:
  - furniture inside the room boundary,
  - furniture dimensions/rotation valid,
  - no duplicate furniture (same uid, or same item_id at ~the same point),
  - every window sits ON a wall and INSIDE its room (else WINDOW_GEOMETRY_INVALID).

Room status is CONFIRMED / UNCERTAIN / EXTRACTION_INVALID / WINDOW_GEOMETRY_INVALID.
Nothing here calls a provider or mutates state — it is safe, read-only.
"""

import math
from typing import Any

from shapely.geometry import LineString, Point, Polygon

from app.services import (
    floor_plan_service,
    furniture_manifest,
    geometry_extraction_service,
    scene_service,
)

# A furniture centre must be within this many world px of some wall line for a
# window to count as "on a wall"; two furniture items of the same type closer
# than this are treated as a duplicate detection.
_WINDOW_WALL_TOL_PX = 45.0
_DUP_CENTER_TOL_PX = 12.0


def _point_seg_dist(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """Distance from point to a finite segment (no shapely dependency needed)."""
    dx, dy = x2 - x1, y2 - y1
    seg2 = dx * dx + dy * dy
    if seg2 <= 1e-9:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / seg2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def _min_wall_dist(x: float, y: float, walls: list[list[float]]) -> float:
    if not walls:
        return float("inf")
    return min(_point_seg_dist(x, y, w[0], w[1], w[2], w[3]) for w in walls)


def _opening_cxy(o: dict[str, Any]) -> tuple[float, float]:
    """Opening centre in world px (normalized cx/cy; x/y fallback for old data)."""
    return float(o.get("cx", o.get("x", 0.0)) or 0.0), float(o.get("cy", o.get("y", 0.0)) or 0.0)


def _in_bbox(x: float, y: float, bbox: list[float], pad: float = 0.0) -> bool:
    bx, by, bw, bh = bbox
    return (bx - pad) <= x <= (bx + bw + pad) and (by - pad) <= y <= (by + bh + pad)


def _furniture_entry(f: dict[str, Any]) -> dict[str, Any]:
    return {
        "uid": f.get("uid") or f.get("id"),
        "item_id": f.get("item_id") or f.get("type"),
        "name": f.get("name"),
        "cx": float(f.get("cx", 0.0)),
        "cy": float(f.get("cy", 0.0)),
        "w": float(f.get("w", 0.0)),
        "h": float(f.get("h", 0.0)),
        "rotation": float(f.get("rotation", 0.0)),
    }


def _duplicate_flags(items: list[dict[str, Any]]) -> list[str]:
    """Duplicate detections: same uid used twice, or the same item_id at ~the
    same centre (an overlapping-tile / double-placement artifact — spec §11)."""
    issues: list[str] = []
    seen_uid: set[str] = set()
    for it in items:
        uid = str(it.get("uid") or "")
        if uid and uid in seen_uid:
            issues.append(f"duplicate uid '{uid}'")
        if uid:
            seen_uid.add(uid)
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i], items[j]
            if a["item_id"] and a["item_id"] == b["item_id"]:
                if math.hypot(a["cx"] - b["cx"], a["cy"] - b["cy"]) <= _DUP_CENTER_TOL_PX:
                    issues.append(
                        f"near-identical {a['item_id']} at ({a['cx']:.0f},{a['cy']:.0f})"
                    )
    return issues


def _room_report(
    room: dict[str, Any], walls: list[list[float]], thickness: float = 0.0
) -> dict[str, Any]:
    label = room.get("label")
    bbox = room.get("bbox") or [0.0, 0.0, 0.0, 0.0]
    raw_items = room.get("furniture", []) or []
    items = [_furniture_entry(f) for f in raw_items]
    doors = room.get("doors", []) or []
    windows = room.get("windows", []) or []

    issues: list[str] = []

    # Furniture validity: inside the room, positive dimensions. A wall-enclosed
    # room's boundary is the eroded interior, so a near-wall item (e.g. a counter)
    # can sit just outside it while still belonging to the room; allow the same
    # few-wall-thicknesses tolerance the assignment uses. Only furniture FAR
    # outside (in another room) is flagged.
    boundary = room.get("boundary") or []
    pad = thickness * 4.0 if thickness > 0 else 2.0
    ring = None
    if len(boundary) >= 4:
        try:
            ring = Polygon([(float(p[0]), float(p[1])) for p in boundary]).buffer(pad)
        except (TypeError, ValueError, IndexError):
            ring = None

    def _item_outside(it: dict[str, Any]) -> bool:
        if ring is not None:
            return not ring.covers(Point(it["cx"], it["cy"]))
        return not _in_bbox(it["cx"], it["cy"], bbox, pad=pad)

    outside = [it["item_id"] for it in items if _item_outside(it)]
    if outside:
        issues.append(f"furniture outside room boundary: {outside}")
    bad_dims = [it["item_id"] for it in items if it["w"] <= 0 or it["h"] <= 0]
    if bad_dims:
        issues.append(f"non-positive furniture dimensions: {bad_dims}")

    issues.extend(_duplicate_flags(items))

    # Window validity (spec §8 / goal §3): every window must sit ON a wall AND
    # inside the room. For an ARCHITECTURAL room the authoritative inside-room test
    # is Polygon(boundary).covers(Point(cx,cy)) — NEVER the bbox (which would count
    # a window in an L-shaped room's notch as inside). The polygon is buffered by
    # the wall thickness so a window embedded in the room's own bounding wall (just
    # outside the eroded interior) still counts as inside. A window outside the
    # architectural polygon → WINDOW_GEOMETRY_INVALID. Fallback/furniture rooms use
    # the bbox as diagnostic context only and stay UNCERTAIN regardless.
    is_arch_room = str(room.get("geometry_source", "")).startswith("architectural")
    arch_poly = None
    if is_arch_room and len(boundary) >= 4:
        try:
            base_poly = Polygon([(float(p[0]), float(p[1])) for p in boundary])
            arch_poly = base_poly.buffer(thickness) if thickness > 0 else base_poly
        except (TypeError, ValueError, IndexError):
            arch_poly = None

    window_report: list[dict[str, Any]] = []
    window_invalid = False
    for w in windows:
        wx, wy = _opening_cxy(w)
        d = _min_wall_dist(wx, wy, walls)
        on_wall = bool(w["on_wall"]) if "on_wall" in w else (d <= _WINDOW_WALL_TOL_PX)
        if arch_poly is not None:
            inside_test = "polygon"
            in_room = bool(arch_poly.covers(Point(wx, wy)))
            # A window off the wall OR outside the real architectural polygon is
            # geometry-invalid (tested against the polygon, not the bbox).
            if not on_wall or not in_room:
                window_invalid = True
        else:
            inside_test = "bbox"
            in_room = _in_bbox(wx, wy, bbox, pad=_WINDOW_WALL_TOL_PX)
        window_report.append(
            {
                "id": w.get("id"),
                "kind": w.get("kind", "window"),
                "supporting_wall_id": w.get("supporting_wall_id") or w.get("wall_id"),
                "cx": round(wx, 1),
                "cy": round(wy, 1),
                "w": w.get("w"),
                "h": w.get("h"),
                "rotation": w.get("rotation"),
                "source": w.get("source"),
                "on_wall": on_wall,
                "dist_to_nearest_wall_px": None if math.isinf(d) else round(d, 1),
                "inside_room": in_room,
                "inside_test": inside_test,
                "uncertain": w.get("uncertain", False),
                "uncertain_reason": w.get("uncertain_reason"),
            }
        )

    # Door reports carry the proven wall link (a door sits in a wall GAP, so it is
    # not required to be on wall material — we just surface whether it proved a
    # wall association).
    door_report = []
    for d in doors:
        dx, dy = _opening_cxy(d)
        door_report.append({
            "id": d.get("id"),
            "kind": d.get("kind", "door"),
            "supporting_wall_id": d.get("supporting_wall_id") or d.get("wall_id"),
            "cx": round(dx, 1),
            "cy": round(dy, 1),
            "w": d.get("w"),
            "h": d.get("h"),
            "rotation": d.get("rotation"),
            "source": d.get("source"),
            "on_wall": d.get("on_wall"),
            "assignment": d.get("assignment"),
            "uncertain": d.get("uncertain", False),
            "uncertain_reason": d.get("uncertain_reason"),
        })

    # Boundary validation: a real architectural room needs a closed, non-zero-area
    # polygon; a fallback room legitimately has none proven.
    boundary = room.get("boundary") or []
    boundary_valid = False
    if len(boundary) >= 4:
        try:
            boundary_valid = Polygon(
                [(float(p[0]), float(p[1])) for p in boundary]
            ).area > 0.0
        except (TypeError, ValueError, IndexError):
            boundary_valid = False

    manifest = furniture_manifest.build_room_manifest(raw_items)

    rejection_reasons: list[str] = []
    if window_invalid:
        status = "WINDOW_GEOMETRY_INVALID"
    elif issues:
        status = "EXTRACTION_INVALID"
    elif room.get("geometry_source") != "architectural":
        # Rooms with no proven wall cycle are geometry-honest but not
        # architecturally confirmed — flag as UNCERTAIN, never silently "ok".
        status = "UNCERTAIN"
        rejection_reasons.append("no proven wall cycle - furniture-fallback boundary")
    elif not boundary_valid:
        status = "UNCERTAIN"
        rejection_reasons.append("architectural room without a valid closed boundary")
    else:
        status = "CONFIRMED"

    return {
        "room": room.get("id"),
        "label": label,
        "geometry_source": room.get("geometry_source"),
        "scene_validation_status": room.get("validation_status"),
        "supporting_wall_ids": room.get("supporting_wall_ids", []),
        "boundary_valid": boundary_valid,
        "bbox": bbox,
        "dimensions": room.get("dimensions"),
        "door_count": len(doors),
        "doors": door_report,
        "window_count": len(windows),
        "window_wall_ids": [w.get("supporting_wall_id") or w.get("wall_id") for w in windows],
        "windows": window_report,
        "furniture_count": len(items),
        "furniture_ids": [it["item_id"] for it in items],
        "furniture": items,
        "manifest": manifest,
        "issues": issues,
        "rejection_reasons": rejection_reasons,
        "status": status,
    }


def _wall_connectivity(structured_walls: list[dict[str, Any]]) -> dict[str, Any]:
    """Explain WHY the walls do (not) form closed room polygons (spec §2).

    Architectural room boundaries can only be reconstructed when wall segments
    share endpoints (a connected graph). This measures endpoint isolation and the
    polygonization result so a `furniture_fallback` room is explained, never
    silently accepted.
    """
    from shapely.ops import polygonize, unary_union

    pts: list[tuple[float, float]] = []
    lines = []
    for w in structured_walls:
        a = (float(w["x1"]), float(w["y1"]))
        b = (float(w["x2"]), float(w["y2"]))
        pts.extend([a, b])
        if math.hypot(a[0] - b[0], a[1] - b[1]) > 1.0:
            lines.append(LineString([a, b]))
    tol = 12.0
    isolated = 0
    for i, p in enumerate(pts):
        nearest = min(
            (math.hypot(p[0] - q[0], p[1] - q[1]) for j, q in enumerate(pts) if j != i),
            default=9e9,
        )
        if nearest > tol:
            isolated += 1
    polys = list(polygonize(unary_union(lines))) if lines else []
    return {
        "wall_count": len(structured_walls),
        "endpoint_count": len(pts),
        "isolated_endpoints_12px": isolated,
        "polygons_formed": len(polys),
        "forms_closed_rooms": len([p for p in polys if p.area >= 4000.0]) > 0,
        "note": (
            "walls are too fragmented/disconnected to reconstruct closed room "
            "boundaries; rooms fall back to a furniture-derived bbox (no invented "
            "geometry)" if isolated > len(pts) * 0.4 else "walls form a connected graph"
        ),
    }


def build_extraction_report(file_id: str) -> dict[str, Any]:
    """Deterministic SOURCE→CANONICAL→SCENE→VALIDATION report for every room."""
    canonical = floor_plan_service.get_canonical(file_id)
    _path, file_type, _ = floor_plan_service.get_floor_plan_file(file_id)
    scene = scene_service.build_scene(file_id)

    walls = scene.get("walls", []) or []
    structured_walls = scene.get("structured_walls", []) or []
    rooms = scene.get("rooms", []) or []
    thickness = 0.0
    try:
        from app.services import wall_reconstruction

        segs = [tuple(map(float, w[:4])) for w in walls
                if (w[2] - w[0]) ** 2 + (w[3] - w[1]) ** 2 > 0]
        if segs:
            thickness = float(wall_reconstruction.measure_tolerances(segs)["thickness"])
    except Exception:  # noqa: BLE001
        thickness = 0.0
    room_reports = [_room_report(r, walls, thickness) for r in rooms]

    # Topology summary. The AUTHORITATIVE rooms are the wall-enclosed regions in
    # the scene (raster reconstruction for PDF plans); the vector junction graph is
    # reported as a supplementary cross-check. Both come from real walls, never
    # furniture.
    proven_scene = [
        r for r in rooms if str(r.get("geometry_source", "")).startswith("architectural")
    ]
    topology: dict[str, Any] = {
        "authoritative_rooms_proven": len(proven_scene),
        "authoritative_rooms_total": len(rooms),
        "proven_rooms": [
            {"id": r.get("id"), "label": r.get("label"),
             "supporting_wall_count": len(r.get("supporting_wall_ids") or []),
             "area_sqm": (r.get("dimensions") or {}).get("area_sqm")}
            for r in proven_scene
        ],
    }
    if structured_walls:
        try:
            from app.services import wall_reconstruction

            seg = [(w["x1"], w["y1"], w["x2"], w["y2"]) for w in structured_walls]
            recon = wall_reconstruction.reconstruct_rooms_topology(seg)
            topology["vector_junctions"] = {
                "stats": recon.get("stats"),
                "L": recon.get("stats", {}).get("L"),
                "T": recon.get("stats", {}).get("T"),
                "count": len(recon.get("junctions", [])),
            }
        except Exception:  # noqa: BLE001 — diagnostics must never crash
            topology["vector_junctions"] = {"error": "unavailable"}

    any_invalid = any(
        rr["status"] in ("EXTRACTION_INVALID", "WINDOW_GEOMETRY_INVALID")
        for rr in room_reports
    )
    overall = "EXTRACTION_INVALID" if any_invalid else (
        "UNCERTAIN" if any(rr["status"] == "UNCERTAIN" for rr in room_reports) else "CONFIRMED"
    )

    # Extraction-layer geometry diagnostics (walls + first-class PDF openings).
    extraction_geometry: dict[str, Any] = {"file_type": file_type}
    try:
        if file_type == "pdf":
            raw = geometry_extraction_service.extract_walls(str(_path))
            raw_walls = raw.get("walls", []) or []
            raw_openings = raw.get("openings", []) or []
            src = {}
            for s in raw.get("wall_sources", []) or []:
                src[s] = src.get(s, 0) + 1
            doors_o = [o for o in raw_openings if o.get("kind") == "door"]
            windows_o = [o for o in raw_openings if o.get("kind") == "window"]
            extraction_geometry = {
                "file_type": file_type,
                "raw_wall_count": len(raw_walls),
                "wall_source_provenance": src,
                "normalized_wall_count": len(structured_walls),
                "door_count": len(doors_o),
                "window_count": len(windows_o),
                "openings": [
                    {k: o.get(k) for k in (
                        "id", "kind", "cx", "cy", "w", "h", "rotation",
                        "supporting_wall_id", "source", "validation_status",
                        "wall_distance_px", "uncertain", "uncertain_reason")}
                    for o in raw_openings
                ],
                "uncertain_openings": [
                    {"id": o.get("id"), "reason": o.get("uncertain_reason")}
                    for o in raw_openings if o.get("uncertain")
                ],
            }
    except Exception as exc:  # noqa: BLE001 — diagnostics must never crash
        extraction_geometry = {"file_type": file_type, "error": str(exc)}

    canonical_furniture = canonical.get("furniture", []) or []
    return {
        "file_id": file_id,
        "file_type": file_type,
        "page": scene.get("page"),
        "canonical_furniture_count": len(canonical_furniture),
        "canonical_item_ids": [str(f.get("item_id")) for f in canonical_furniture],
        "wall_count": len(walls),
        "extraction_geometry": extraction_geometry,
        "wall_connectivity": _wall_connectivity(structured_walls),
        "topology": topology,
        "scene_geometry_validation": scene.get("geometry_validation"),
        "geometry_invalid": scene.get("geometry_invalid"),
        "room_count": len(room_reports),
        "rooms": room_reports,
        "overall_status": overall,
    }
