"""Canonical room-scene builder for the deterministic 3D renderer.

Composes the single source of truth the Three.js engine consumes: extracted walls
(world px) + furniture grouped into rooms, each with its bounding box and every
item's exact position/size/rotation. No AI decides any of these values
(CLAUDE.md RULE #1).
"""

import math
from typing import Any

from app.services import (
    architectural_service,
    floor_plan_service,
    geometry_extraction_service,
    validation_service,
)


def _slug(label: str) -> str:
    return label.lower().replace(" & ", "-").replace(" ", "-")


def _room_bbox(items: list[dict[str, Any]]) -> list[float]:
    xs = [float(i["cx"]) for i in items]
    ys = [float(i["cy"]) for i in items]
    ws = [float(i["w"]) for i in items]
    hs = [float(i["h"]) for i in items]
    x0 = min(c - w / 2 for c, w in zip(xs, ws, strict=False))
    x1 = max(c + w / 2 for c, w in zip(xs, ws, strict=False))
    y0 = min(c - h / 2 for c, h in zip(ys, hs, strict=False))
    y1 = max(c + h / 2 for c, h in zip(ys, hs, strict=False))
    return [x0, y0, x1 - x0, y1 - y0]


def select_bridge_openings(
    pdf_openings: list[dict[str, Any]] | None,
    furniture: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Openings used to bridge room topology (goal §1/§2).

    When the plan carries its OWN PDF opening geometry, only the VALIDATED PDF
    doors/windows may bridge — never canonical furniture named door/window, and
    never an UNCERTAIN/INVALID opening. If no validated openings exist among them,
    bridge none. Furniture door/window items are used ONLY as a fallback when the plan
    has no PDF opening geometry (pdf_openings is None or empty).
    """
    if pdf_openings:
        return [
            o for o in pdf_openings
            if o.get("validation_status") == "VALID" and not o.get("uncertain")
        ]
    return [
        f for f in furniture
        if "door" in str(f.get("item_id", "")) or "window" in str(f.get("item_id", ""))
    ]


_OPENING_DEDUP_PX = 100.0


def _attach_supplemental_openings(rooms: list[dict[str, Any]]) -> None:
    """Attach per-room `supplemental_doors`/`supplemental_windows`: the PDF-detected
    openings (room['doors']/room['windows']) that no editor-placed opening of the
    same kind sits within `_OPENING_DEDUP_PX` of — deduped GLOBALLY across all rooms
    (shared-wall doors are assigned to one room but placed in the adjacent one).
    Editor placements win; these fill only genuine gaps. Mutates rooms in place;
    adds new keys only (canonical/doors/windows/furniture untouched)."""
    ed_doors: list[tuple[float, float]] = []
    ed_windows: list[tuple[float, float]] = []
    for r in rooms:
        for f in r.get("furniture", []) or []:
            iid = str(f.get("item_id", ""))
            try:
                c = (float(f["cx"]), float(f["cy"]))
            except (KeyError, TypeError, ValueError):
                continue
            if "window" in iid:
                ed_windows.append(c)
            elif "door" in iid:
                ed_doors.append(c)

    def _unmatched(
        openings: list[dict[str, Any]] | None, editors: list[tuple[float, float]]
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for o in openings or []:
            try:
                ox, oy = float(o["cx"]), float(o["cy"])
            except (KeyError, TypeError, ValueError):
                continue
            if not any(math.hypot(ox - ex, oy - ey) < _OPENING_DEDUP_PX for ex, ey in editors):
                out.append(o)
        return out

    for r in rooms:
        r["supplemental_doors"] = _unmatched(r.get("doors"), ed_doors)
        r["supplemental_windows"] = _unmatched(r.get("windows"), ed_windows)


def _project_on_wall(
    cx: float, cy: float, w: dict[str, Any]
) -> tuple[float, float, float, float, float]:
    """Project (cx,cy) onto structured wall w. Returns (px, py, angle_deg, perp_px,
    along_t) where (px,py) is the foot on the wall segment, angle its direction, perp
    the perpendicular distance, along_t the normalized position along the segment."""
    x1, y1, x2, y2 = float(w["x1"]), float(w["y1"]), float(w["x2"]), float(w["y2"])
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy or 1.0
    t = max(0.0, min(1.0, ((cx - x1) * dx + (cy - y1) * dy) / l2))
    px, py = x1 + t * dx, y1 + t * dy
    return px, py, math.degrees(math.atan2(dy, dx)), math.hypot(cx - px, cy - py), t


def _find_supporting_wall(
    cx: float, cy: float, rot: float, structured_walls: list[dict[str, Any]],
    wall_id: str | None, max_perp: float = 60.0,
) -> dict[str, Any] | None:
    """The authoritative supporting wall for an opening. Prefer an explicit
    supporting_wall_id (PDF openings). Else associate by REAL wall geometry: the
    opening must project WITHIN a wall segment, be close perpendicularly (≤max_perp),
    and its rotation must match the wall direction (never a bbox-aspect guess).
    Returns None when no wall qualifies (caller marks the opening UNABLE_TO_VERIFY —
    never a teleport / invented placement). `max_perp` is larger for doors, whose
    authored center sits further into the room by their leaf depth."""
    if wall_id:
        w = next((x for x in structured_walls if x.get("id") == wall_id), None)
        if w:
            return w
    best = None
    best_perp = 1e9
    for w in structured_walls:
        _px, _py, ang, perp, t = _project_on_wall(cx, cy, w)
        if t <= 0.001 or t >= 0.999:
            continue  # opening projects off the end of this segment
        drot = abs((rot % 180) - (ang % 180))
        drot = min(drot, 180 - drot)
        if drot > 25:
            continue  # rotation must agree with the wall direction
        if perp < best_perp and perp <= max_perp:
            best_perp = perp
            best = w
    return best


def _attach_opening_placements(
    rooms: list[dict[str, Any]], structured_walls: list[dict[str, Any]]
) -> None:
    """Attach per-room `opening_placements`: the AUTHORITATIVE on-wall placement of
    every rendered opening (editor door/window items UNION PDF supplementals). Each
    opening is associated to its real supporting wall (structured geometry, never the
    furniture bbox / room boundary) and PROJECTED onto that wall — so the deterministic
    3D opening sits exactly on its source wall at its source wall-relative position.
    Editor placements keep their authored width/rotation; only the perpendicular
    off-wall drift is removed. Render-only: furniture/walls/rooms data unchanged."""
    for r in rooms:
        placements: list[dict[str, Any]] = []
        cand: list[tuple[str, str, dict[str, Any], str | None]] = []
        for f in r.get("furniture", []) or []:
            iid = str(f.get("item_id", ""))
            if "window" in iid:
                cand.append(("window", "editor", f, f.get("supporting_wall_id")))
            elif "door" in iid:
                cand.append(("door", "editor", f, f.get("supporting_wall_id")))
        for o in r.get("supplemental_windows") or []:
            cand.append(("window", "pdf", o, o.get("supporting_wall_id")))
        for o in r.get("supplemental_doors") or []:
            cand.append(("door", "pdf", o, o.get("supporting_wall_id")))
        for kind, src, o, wid in cand:
            try:
                cx, cy = float(o["cx"]), float(o["cy"])
                w = float(o["w"])
                h = float(o["h"])
                rot = float(o.get("rotation", 0) or 0)
            except (KeyError, TypeError, ValueError):
                continue
            # Doors sit further off the wall centerline (leaf depth), so allow a
            # larger perpendicular gap for them than for thin windows.
            max_perp = 100.0 if kind == "door" else 60.0
            wall = _find_supporting_wall(cx, cy, rot, structured_walls, wid, max_perp)
            base = {
                "id": str(o.get("uid") or o.get("id") or f"{kind}-{len(placements)}"),
                "kind": kind,
                "source": src,
                "w": w,
                "h": h,
                "rotation": rot,
            }
            if wall is None:
                # No authoritative wall — render at the authored position, flagged.
                # Explicit status (self-documenting) so callers/UI never treat an
                # unverified opening as correctly wall-associated. Additive field;
                # geometry/orientation and the `verified` flag are unchanged.
                placements.append({**base, "cx": cx, "cy": cy, "wall_id": None,
                                   "wall_angle_deg": rot, "verified": False,
                                   "status": "NEEDS_REVIEW"})
                continue
            px, py, ang, perp, t = _project_on_wall(cx, cy, wall)
            wlen = math.hypot(float(wall["x2"]) - float(wall["x1"]),
                              float(wall["y2"]) - float(wall["y1"]))
            placements.append({
                **base,
                "cx": px,            # ON the wall (perpendicular drift removed)
                "cy": py,
                "wall_id": wall.get("id"),
                "wall_angle_deg": ang,          # authoritative wall direction
                "wall_relative": {
                    "normalized": round(t, 4),
                    "along_px": round(t * wlen, 2),
                    "perp_removed_px": round(perp, 2),
                    "wall_len_px": round(wlen, 2),
                },
                "verified": True,
                "status": "PLACED",
            })
        r["opening_placements"] = placements


def build_scene(file_id: str, canonical: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return {page, walls, rooms[]} — everything in world px (world = pdf_pt × scale).

    ``canonical`` lets a caller pass a FROZEN design snapshot (its furniture) so the
    scene is built against an immutable generation snapshot rather than the live,
    latest layout. When omitted, the current authoritative canonical is read. The
    architectural geometry (walls/doors/windows) is always derived from the immutable
    floor-plan file, so geometry rules are identical either way — only the furniture
    source changes.
    """
    path, file_type, _ = floor_plan_service.get_floor_plan_file(file_id)
    if canonical is None:
        canonical = floor_plan_service.get_canonical(file_id)
    furniture = canonical.get("furniture", []) or []

    walls: list[list[float]] = []
    wall_colors: list[str] = []
    pdf_openings: list[dict[str, Any]] | None = None
    page: dict[str, float] = {"width": 1000.0, "height": 750.0, "scale": 1.0}
    if file_type == "pdf":
        try:
            geometry = geometry_extraction_service.extract_walls(str(path))
            walls = geometry["walls"]
            wall_colors = geometry.get("wall_colors", [])
            pdf_openings = geometry.get("openings", [])
            page = geometry["page"]
        except Exception:  # noqa: BLE001 — a plan without vectors still renders furniture
            walls = []
            wall_colors = []
            pdf_openings = []

    # Drop detached annotation/detail blocks drawn *below* the inhabited plan
    # (legend, section detail, title strip). They are separated from the real
    # rooms by a clear vertical gap, so anything wholly below that gap is markup,
    # not architecture.
    if walls and furniture:
        fy0 = min(float(i["cy"]) - float(i["h"]) / 2 for i in furniture)
        fy1 = max(float(i["cy"]) + float(i["h"]) / 2 for i in furniture)
        tops_below = sorted(min(w[1], w[3]) for w in walls if min(w[1], w[3]) > fy1)
        if tops_below and (tops_below[0] - fy1) > max(40.0, (fy1 - fy0) * 0.03):
            cut = tops_below[0] - 1.0
            kept_w: list[list[float]] = []
            kept_c: list[str] = []
            dropped_len = 0.0
            for idx, w in enumerate(walls):
                if min(w[1], w[3]) < cut:
                    kept_w.append(w)
                    if idx < len(wall_colors):
                        kept_c.append(wall_colors[idx])
                else:
                    dropped_len += math.hypot(w[2] - w[0], w[3] - w[1])
            total_len = sum(math.hypot(w[2] - w[0], w[3] - w[1]) for w in walls)
            # Item 20 — proven-safe guard: only discard the detached block below
            # the plan when it is a small MINORITY of total wall length (a legend
            # / title strip). If the "below" region carries a large share of the
            # walls it is legitimate architecture, so keep every wall.
            if total_len > 0 and dropped_len / total_len <= 0.25:
                walls = kept_w
                wall_colors = kept_c

    # 1. Build structured walls from architectural geometry
    structured_walls = architectural_service.build_structured_walls(walls, wall_colors)

    # 2. Enrich furniture with exact wall relationships
    enriched_furniture = architectural_service.enrich_furniture_relationships(
        furniture, structured_walls
    )

    # 3. Doors and windows as first-class ARCHITECTURAL entities — PRIMARY source
    # is the PDF's own door(gold)/window(cyan) geometry (normalized to the same
    # world coords + supporting_wall_id in geometry_extraction_service). Furniture
    # naming is only a fallback for plans with no opening geometry.
    doors, windows = architectural_service.extract_doors_and_windows(
        structured_walls, enriched_furniture, pdf_openings=pdf_openings
    )

    # 4a. Authoritative wall-enclosed rooms from the SOURCE drawing.
    # Single resolution chain:
    # 1. Vector planar cycle topology (preferred)
    # 2. Raster contour reconstruction (deterministic aid when vector lines have gaps)
    # 3. Bounding-box / convex-hull fallback (uncertain / fallback ONLY)
    proven_rooms: list[dict[str, Any]] | None = None
    if file_type == "pdf" and structured_walls:
        try:
            from app.services import room_reconstruction_raster, wall_reconstruction

            segs: list[tuple[float, float, float, float]] = [
                (float(w[0]), float(w[1]), float(w[2]), float(w[3]))
                for w in walls
                if (w[2] - w[0]) ** 2 + (w[3] - w[1]) ** 2 > 0
            ]
            thickness = wall_reconstruction.measure_tolerances(segs)["thickness"] if segs else 0.0
            bridge_openings = select_bridge_openings(pdf_openings, furniture)
            if thickness > 0:
                proven_rooms = room_reconstruction_raster.reconstruct_rooms_raster(
                    str(path), walls, bridge_openings, thickness
                )["rooms"]
        except Exception:  # noqa: BLE001 — fall back to vector topology on any failure
            proven_rooms = None

    # 4b. Reconstruct room entities; furniture is assigned to the proven rooms.
    # Openings are the authoritative PDF doors/windows (assigned to rooms here).
    rooms = architectural_service.reconstruct_rooms(
        enriched_furniture, structured_walls, doors=doors, windows=windows,
        proven_rooms=proven_rooms,
    )

    # MERGE (union, dedup) for doors/windows rendering: attach to each room the
    # PDF-detected openings the editor did NOT place, so the deterministic 3D/base
    # render shows every real, wall-owned opening (goal: no missing door/window).
    # Editor placements always win. Dedup is GLOBAL (against every room's editor
    # openings) because a door on a shared wall is assigned to one room in the PDF
    # but placed in the adjacent room by the editor. This ONLY adds per-room
    # `supplemental_doors`/`supplemental_windows` fields (read by the renderer); it
    # does NOT alter canonical furniture, room.doors/room.windows, walls, or the
    # §L validation (which reads only doors/windows/furniture).
    _attach_supplemental_openings(rooms)
    # AUTHORITATIVE opening placement: project every rendered opening onto its real
    # supporting wall (structured geometry), so the deterministic 3D opening sits on
    # its source wall — not snapped to the furniture-bbox room boundary.
    _attach_opening_placements(rooms, structured_walls)

    scene: dict[str, Any] = {
        "page": page,
        "walls": walls,
        "wall_colors": wall_colors,
        "structured_walls": structured_walls,
        "doors": doors,
        "windows": windows,
        "rooms": rooms,
    }
    # Self-validate the reconstruction against the authoritative canonical plan
    # (spec §L): every furniture item preserved, openings room-specific, and
    # architectural rooms carry a closed boundary. A non-faithful scene here
    # means the base render (and any AI render built on it) is not trustworthy.
    scene["geometry_validation"] = validation_service.validate_scene_against_canonical(
        canonical, scene
    )
    # Item 18 — flag (do not silently continue with) a geometry-invalid scene so
    # the caller / renderer can refuse to treat it as a faithful base. We flag
    # rather than raise: a furniture-only plan with no provable walls still
    # renders its furniture, but is honestly marked not geometry-faithful.
    # Goal §5: geometry_invalid is true WHENEVER the scene is not geometry-faithful
    # — never masked just because walls were extracted. geometry_source and
    # validation_status stay explicit (per room + per opening) for diagnostics.
    faithful = bool(scene["geometry_validation"].get("geometry_faithful"))
    scene["geometry_source"] = "pdf_vector" if file_type == "pdf" and walls else "furniture_only"
    scene["validation_status"] = "GEOMETRY_FAITHFUL" if faithful else "GEOMETRY_MISMATCH"
    scene["geometry_invalid"] = not faithful
    if scene["geometry_invalid"]:
        scene["geometry_invalid_reasons"] = scene["geometry_validation"].get("mismatches", [])
    return scene

