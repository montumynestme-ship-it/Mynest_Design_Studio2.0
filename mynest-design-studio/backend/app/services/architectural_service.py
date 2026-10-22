"""Architectural geometry reconstruction, room polygon analysis, and wall relationships.

Provides deterministic structural understanding from extracted vector walls:
1. Structured walls with ID, length, angle, thickness, and height.
2. Closed architectural room boundary reconstruction with fallback tracking.
3. Furniture-to-wall relationships: nearest wall ID, distance in px and mm, adjacency.
4. Structured door and window representation.
"""

import math
from typing import Any

from shapely.geometry import LineString, Point, Polygon

from app.data import furniture_catalog
from app.services import prompt_service
from app.services.coordinates import DEFAULT_MPP, world_to_mm


def build_structured_walls(
    walls: list[list[float]], wall_colors: list[str] | None = None
) -> list[dict[str, Any]]:
    """Convert raw line segments into structured wall entities."""
    colors = wall_colors or []
    structured: list[dict[str, Any]] = []

    for idx, w in enumerate(walls):
        x1, y1, x2, y2 = w
        length = math.hypot(x2 - x1, y2 - y1)
        angle = math.degrees(math.atan2(y2 - y1, x2 - x1)) % 360.0
        color = colors[idx] if idx < len(colors) else "#141414"
        # NOTE: a wall's COLOR is NOT treated as a window signal anymore. Arbitrary
        # colored PDF/vector strokes were being misread as windows (spec goal §3).
        # Windows come ONLY from canonical window items / real opening geometry.
        is_window = False

        structured.append(
            {
                "id": f"wall_{idx + 1:03d}",
                "x1": round(x1, 2),
                "y1": round(y1, 2),
                "x2": round(x2, 2),
                "y2": round(y2, 2),
                "length": round(length, 2),
                "angle_deg": round(angle, 2),
                "thickness": 10.0,
                "height": 2.7,
                "is_window": is_window,
                "color": color,
            }
        )
    return structured


def _opening_xy(o: dict[str, Any]) -> tuple[float, float]:
    """Opening centre in world px. Canonical schema is cx/cy; x/y kept as a
    backward-compatible fallback so no x/y-vs-cx/cy mismatch can reappear."""
    cx = o.get("cx", o.get("x", 0))
    cy = o.get("cy", o.get("y", 0))
    return float(cx or 0), float(cy or 0)


def extract_doors_and_windows(
    structured_walls: list[dict[str, Any]],
    furniture: list[dict[str, Any]],
    pdf_openings: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Doors and windows as first-class ARCHITECTURAL entities.

    PRIMARY source is the PDF's own door/window geometry (``pdf_openings`` from
    geometry_extraction_service, already normalized to id/kind/cx/cy/w/h/rotation/
    supporting_wall_id). Canonical furniture whose item_id merely contains
    "door"/"window" is only a FALLBACK when the PDF has no opening geometry — it
    must never be the primary architectural source (spec: openings come from the
    drawing, not from furniture naming).
    """
    if pdf_openings is not None:
        doors = [dict(o) for o in pdf_openings if o.get("kind") == "door"]
        windows = [dict(o) for o in pdf_openings if o.get("kind") == "window"]
        return doors, windows
    return _doors_windows_from_furniture(structured_walls, furniture)


def _doors_windows_from_furniture(
    structured_walls: list[dict[str, Any]], furniture: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """FALLBACK only: derive openings from canonical door/window items when the PDF
    carries no opening geometry. Emits the same cx/cy schema."""
    doors: list[dict[str, Any]] = []
    windows: list[dict[str, Any]] = []

    # 1. Furniture catalog doors/windows
    door_idx = 1
    win_idx = 1
    for f in furniture:
        item_id = str(f.get("item_id", ""))
        if "door" in item_id:
            doors.append(
                {
                    "id": f"door_{door_idx:03d}",
                    "kind": "door",
                    "cx": float(f["cx"]),
                    "cy": float(f["cy"]),
                    "w": float(f["w"]),
                    "h": float(f["h"]),
                    "rotation": float(f.get("rotation", 0)),
                    "supporting_wall_id": f.get("nearest_wall_id"),
                    "source": "furniture_fallback",
                    "room_id": f.get("room_id"),
                }
            )
            door_idx += 1
        elif "window" in item_id:
            windows.append(
                {
                    "id": f"window_{win_idx:03d}",
                    "kind": "window",
                    "cx": float(f["cx"]),
                    "cy": float(f["cy"]),
                    "w": float(f["w"]),
                    "h": float(f["h"]),
                    "rotation": float(f.get("rotation", 0)),
                    "supporting_wall_id": f.get("nearest_wall_id"),
                    "source": "furniture_fallback",
                    "room_id": f.get("room_id"),
                }
            )
            win_idx += 1

    # 2. Color-coded "window layer" heuristic REMOVED (spec goal §3): a wall being
    # a non-black color no longer fabricates a window. Windows are authoritative
    # only from canonical window items (step 1) or real opening geometry. This
    # stops arbitrary colored strokes from becoming phantom windows.

    return doors, windows


def calculate_wall_relationship(
    item: dict[str, Any],
    structured_walls: list[dict[str, Any]],
    mpp: float = DEFAULT_MPP,
) -> dict[str, Any]:
    """Calculate exact wall relationship for a single furniture item.

    Returns:
        nearest_wall_id, distance_px, distance_to_wall_mm, relationship
    """
    if not structured_walls:
        return {
            "nearest_wall_id": None,
            "distance_px": 9999.0,
            "distance_to_wall_mm": 99990.0,
            "relationship": "freestanding",
        }

    cx = float(item["cx"])
    cy = float(item["cy"])
    half_extent = min(float(item["w"]), float(item["h"])) / 2.0
    pt = Point(cx, cy)

    min_dist = float("inf")
    nearest_id: str | None = None

    for w in structured_walls:
        line = LineString([(w["x1"], w["y1"]), (w["x2"], w["y2"])])
        dist = pt.distance(line)
        if dist < min_dist:
            min_dist = dist
            nearest_id = w["id"]

    dist_mm = world_to_mm(min_dist, mpp)
    # Adjacency check: distance to wall surface (accounting for furniture half-extent)
    surface_dist_mm = max(0.0, dist_mm - world_to_mm(half_extent, mpp))

    # Ordering fix (spec §7D): test the tightest band FIRST, else the <=50
    # "attached" branch was unreachable behind <=150. Touching items (center
    # within half-extent of the wall) are attached; near items adjacent; else free.
    if surface_dist_mm <= 50.0 or min_dist <= half_extent + 15.0:
        rel = "attached"
    elif surface_dist_mm <= 150.0:
        rel = "adjacent"
    else:
        rel = "freestanding"

    return {
        "nearest_wall_id": nearest_id,
        "distance_px": round(min_dist, 2),
        "distance_to_wall_mm": round(dist_mm, 1),
        "relationship": rel,
    }


def enrich_furniture_relationships(
    furniture: list[dict[str, Any]],
    structured_walls: list[dict[str, Any]],
    mpp: float = DEFAULT_MPP,
) -> list[dict[str, Any]]:
    """Enrich each furniture item with exact wall metrics and physical sizes in mm."""
    enriched = []
    for f in furniture:
        rel = calculate_wall_relationship(f, structured_walls, mpp)
        w_mm = world_to_mm(float(f["w"]), mpp)
        h_mm = world_to_mm(float(f["h"]), mpp)

        item = dict(f)
        item["name"] = f.get("name") or furniture_catalog.describe(str(f["item_id"]))[0]
        item["real_width_mm"] = round(w_mm, 1)
        item["real_depth_mm"] = round(h_mm, 1)
        item["nearest_wall_id"] = rel["nearest_wall_id"]
        item["distance_to_wall_mm"] = rel["distance_to_wall_mm"]
        item["wall_relationship"] = rel["relationship"]
        item["locked"] = bool(f.get("locked", True))
        enriched.append(item)

    return enriched


def reconstruct_rooms(
    furniture: list[dict[str, Any]],
    structured_walls: list[dict[str, Any]],
    mpp: float = DEFAULT_MPP,
    doors: list[dict[str, Any]] | None = None,
    windows: list[dict[str, Any]] | None = None,
    proven_rooms: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Reconstruct architectural room entities with boundaries, dimensions, doors,
    windows, and geometry source.

    ``proven_rooms`` (optional) are authoritative wall-enclosed room polygons
    already reconstructed from the source drawing (e.g. the raster reconstruction
    in :mod:`room_reconstruction_raster`, which build_scene supplies for PDF
    plans). When given they are the room source; otherwise rooms are proven here
    from the vector wall topology. Either way, furniture is only ASSIGNED to a
    proven room afterwards — it never creates a room.
    """
    # Room-tag annotations carry no geometry — strip them before any room assignment
    # or rendering so a tag can never become a 3D object or affect room reconstruction.
    furniture = furniture_catalog.strip_annotations(furniture)
    if doors is None or windows is None:
        extracted_doors, extracted_windows = extract_doors_and_windows(structured_walls, furniture)
        if doors is None:
            doors = extracted_doors
        if windows is None:
            windows = extracted_windows

    # ---- AUTHORITATIVE room source: wall-enclosed polygons proven from the real
    # drawing. Furniture NEVER creates a room; there is no generic
    # polygonize(raw walls) authority and no furniture-bbox/proximity room
    # creation. Furniture is only ASSIGNED to a proven room afterwards.
    from app.services import wall_reconstruction

    topo_thickness = 0.0
    proven: list[dict[str, Any]] = []
    if proven_rooms is not None:
        # Supplied by build_scene from the authoritative reconstruction.
        proven = [rp for rp in proven_rooms if rp.get("wall_supported")]
    if structured_walls:
        try:
            seg: list[tuple[float, float, float, float]] = [
                (float(w["x1"]), float(w["y1"]), float(w["x2"]), float(w["y2"]))
                for w in structured_walls
                if (float(w["x2"]) - float(w["x1"])) ** 2
                + (float(w["y2"]) - float(w["y1"])) ** 2 > 0
            ]
            tol = wall_reconstruction.measure_tolerances(seg)
            topo_thickness = float(tol.get("thickness") or 0.0)
            if proven_rooms is None:
                recon = wall_reconstruction.reconstruct_rooms_topology(seg, furniture)
                proven = [rp for rp in recon["rooms"] if rp.get("wall_supported")]
        except Exception:  # noqa: BLE001 — reconstruction must never crash the pipeline
            if proven_rooms is None:
                proven = []

    proven_polys = [Polygon(rp["polygon"]) for rp in proven]

    # Wall-ownership map: which proven room(s) list each wall id as a supporting
    # wall. Used to associate a WALL-EMBEDDED item (a door/window symbol or a
    # wall-mounted counter whose centre sits in the wall band, outside the eroded
    # interior polygon) with the room whose wall it physically sits on. This is
    # provenance-based ownership, NOT broad nearest-room guessing: it fires only
    # when the item's own supporting wall belongs to exactly one proven room.
    wall_owner: dict[str, set[int]] = {}
    for i, rp in enumerate(proven):
        for wid in rp.get("supporting_wall_ids", []) or []:
            wall_owner.setdefault(str(wid), set()).add(i)

    # group_by_room only LABELS furniture and groups the unproven leftovers; it
    # never creates an architectural room.
    groups = prompt_service.group_by_room(furniture)

    # Assign each furniture item to the proven room whose polygon geometrically
    # CONTAINS its centre. An item inside no polygon is then associated by
    # WALL-OWNERSHIP: if its nearest supporting wall belongs to exactly one proven
    # room, it sits in that room's wall and is assigned there. Only when neither
    # containment nor unambiguous wall-ownership resolves it does it stay in a
    # non-authoritative UNCERTAIN fallback group. There is NO broad nearest-room
    # reassignment, and furniture coordinates are never altered here.
    proven_entries: dict[int, list[tuple[str, dict[str, Any]]]] = {
        i: [] for i in range(len(proven))
    }
    # Wall-owned items are added to a room for RENDERING but kept OUT of the room's
    # label vote — a door/window symbol or a wall counter pulled in by wall-ownership
    # must never flip the room's identity (e.g. Kitchen → Dining).
    proven_wallowned: dict[int, list[dict[str, Any]]] = {i: [] for i in range(len(proven))}
    leftover: dict[str, list[dict[str, Any]]] = {}
    for label, items in groups:
        for it in items:
            pt = Point(float(it["cx"]), float(it["cy"]))
            matched = next(
                (i for i, poly in enumerate(proven_polys) if poly.covers(pt)), None
            )
            if matched is not None:
                proven_entries[matched].append((label, it))
                continue
            owners = wall_owner.get(str(it.get("nearest_wall_id")), set())
            if len(owners) == 1:
                idx = next(iter(owners))
                it["room_assignment_method"] = "wall_ownership"
                proven_wallowned[idx].append(it)
            else:
                leftover.setdefault(label, []).append(it)

    def _majority(entries: list[tuple[str, dict[str, Any]]], fallback: str) -> str:
        # One physical room may enclose two open-plan sections (e.g. Kitchen +
        # Dining with no wall between them); name it for every section with real
        # presence so neither is lost.
        counts: dict[str, int] = {}
        for lbl, _ in entries:
            counts[lbl] = counts.get(lbl, 0) + 1
        if not counts:
            return fallback
        top = max(counts.values())
        # A section is co-major when its contained-furniture count is a real
        # fraction (>= half) of the dominant section, with a small absolute floor
        # that filters a lone stray item in a busy room. The floor is capped at
        # `top` so it can NEVER exceed the achievable maximum: without the cap an
        # open-plan polygon holding exactly one item per section (top == 1, e.g.
        # Kitchen=1 + Dining=1) clears NO section, the multi-label branch empties,
        # and one genuinely-present section is silently dropped. Capping at `top`
        # keeps every equally-represented section. For top >= 2 this is identical
        # to the previous max(2, top*0.5); it only changes the all-singleton case.
        inclusion = min(top, max(2, top * 0.5))
        major = [lbl for lbl, c in counts.items() if c >= inclusion]
        order = [lbl for lbl, _ in entries]
        major.sort(key=order.index)
        return " & ".join(dict.fromkeys(major)) if len(major) > 1 else max(
            counts.items(), key=lambda kv: kv[1])[0]

    used_slugs: set[str] = set()

    def _slugify(label: str) -> str:
        base = label.lower().replace(" & ", "-").replace(" ", "-")
        slug, n = base, 2
        while slug in used_slugs:
            slug = f"{base}-{n}"
            n += 1
        used_slugs.add(slug)
        return slug

    resolved: list[dict[str, Any]] = []
    # (a) authoritative rooms — one per proven wall cycle (kept even if empty).
    for i, rp in enumerate(proven):
        entries = proven_entries[i]
        label = _majority(entries, f"Room {i + 1}")
        room_items = [it for _, it in entries] + proven_wallowned[i]
        geom_src = rp.get("geom_source", "architectural")
        method = rp.get("assign_method") or (
            "raster_contour" if proven_rooms is not None else "vector_topology"
        )
        resolved.append(
            {
                "slug": _slugify(label),
                "label": label,
                "items": room_items,
                "bbox": rp["bbox"],
                "boundary": [tuple(p) for p in rp["polygon"]],
                "geom_source": geom_src,
                "geometry_source": geom_src,
                "assign_method": method,
                "room_assignment_method": method,
                "supporting_wall_ids": rp.get("supporting_wall_ids", []),
                "status": "CONFIRMED",
            }
        )
    # (b) non-authoritative fallback rooms for furniture the walls could not prove
    # — marked UNCERTAIN, never presented as architectural truth.
    for label, items in leftover.items():
        if not items:
            continue
        xs = [float(i["cx"]) for i in items]
        ys = [float(i["cy"]) for i in items]
        ws = [float(i["w"]) for i in items]
        hs = [float(i["h"]) for i in items]
        pad = 20.0
        x0 = min(c - w / 2 for c, w in zip(xs, ws, strict=False)) - pad
        x1 = max(c + w / 2 for c, w in zip(xs, ws, strict=False)) + pad
        y0 = min(c - h / 2 for c, h in zip(ys, hs, strict=False)) - pad
        y1 = max(c + h / 2 for c, h in zip(ys, hs, strict=False)) + pad
        geom_src = "fallback"
        method = "furniture_hull"
        resolved.append(
            {
                "slug": _slugify(label),
                "label": label,
                "items": items,
                "bbox": [round(x0, 2), round(y0, 2), round(x1 - x0, 2), round(y1 - y0, 2)],
                "boundary": [
                    (round(x0, 2), round(y0, 2)),
                    (round(x1, 2), round(y0, 2)),
                    (round(x1, 2), round(y1, 2)),
                    (round(x0, 2), round(y1, 2)),
                    (round(x0, 2), round(y0, 2)),
                ],
                "geom_source": geom_src,
                "geometry_source": geom_src,
                "assign_method": method,
                "room_assignment_method": method,
                "supporting_wall_ids": [],
                "status": "UNCERTAIN",
            }
        )

    # Second pass: assign each opening to exactly one room by real BOUNDARY-POLYGON
    # containment (not bbox), preferring the room whose wall the opening proved to
    # sit on. If it lies in no room polygon it is placed in the nearest room for
    # rendering but tagged assignment="uncertain" (goal: never a bbox/nearest-only
    # authoritative assignment; mark UNCERTAIN instead).
    room_polys = [Polygon(r["boundary"]) if len(r["boundary"]) >= 4 else None for r in resolved]

    def _assign_openings(openings: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
        by_room: dict[int, list[dict[str, Any]]] = {i: [] for i in range(len(resolved))}
        for o in openings:
            ox, oy = _opening_xy(o)
            pt = Point(ox, oy)
            wall_id = o.get("wall_id")
            containing = [
                i for i, poly in enumerate(room_polys)
                if poly is not None and poly.covers(pt)
            ]
            # Prefer a containing room that also owns the opening's proven wall.
            if wall_id and containing:
                on_wall_rooms = [
                    i for i in containing
                    if wall_id in (resolved[i].get("supporting_wall_ids") or [])
                ]
                containing = on_wall_rooms or containing
            # WALL-OWNERSHIP: an opening sits IN the wall, so its centre is normally
            # outside every eroded interior polygon. When it is contained in none,
            # associate it with the room(s) whose supporting walls include its own
            # proven wall — the room the opening physically belongs to. Unique owner
            # → that room; a shared party wall → the owning room whose boundary is
            # nearest (a tie-break CONSTRAINED to the wall's owners, never a global
            # nearest-room guess).
            wall_owners = (
                [i for i in range(len(resolved))
                 if wall_id in (resolved[i].get("supporting_wall_ids") or [])]
                if wall_id else []
            )
            if containing:
                best = containing[0]
                o["assignment"] = "contained"
            elif len(wall_owners) == 1:
                best = wall_owners[0]
                o["assignment"] = "wall_owned"
            elif len(wall_owners) > 1:
                best = min(
                    wall_owners,
                    key=lambda i: room_polys[i].distance(pt) if room_polys[i] else math.inf,
                )
                o["assignment"] = "wall_owned"
            elif resolved:
                def _center_dist(r: dict[str, Any], ox: float = ox, oy: float = oy) -> float:
                    bx, by, bw, bh = r["bbox"]
                    return math.hypot(ox - (bx + bw / 2), oy - (by + bh / 2))

                best = min(range(len(resolved)), key=lambda i: _center_dist(resolved[i]))
                o["assignment"] = "uncertain"
            else:
                continue
            # Goal §4: an opening is CONFIRMED only when it is tied to a real wall
            # AND it belongs to an ARCHITECTURAL room either by polygon containment
            # or by owning that room's wall. An opening off every wall or landing in
            # a fallback room stays UNCERTAIN.
            room_is_arch = str(resolved[best].get("geom_source", "")).startswith("architectural")
            confirmed = (
                bool(o.get("on_wall"))
                and o["assignment"] in ("contained", "wall_owned")
                and room_is_arch
            )
            o["validation_status"] = "CONFIRMED" if confirmed else "UNCERTAIN"
            by_room[best].append(o)
        return by_room

    # Tie each opening to the nearest REAL wall segment (item 9/17). A door's
    # canonical centre sits mid-doorway (offset from the wall line by ~half a door
    # leaf), so doors use a wider tolerance than windows; this is door-symbol
    # geometry, not gap-bridging. An opening near no wall stays on_wall=False
    # (honest — e.g. a mis-placed window is flagged, not silently accepted).
    if structured_walls:
        wall_lines = [
            (w["id"], LineString([(w["x1"], w["y1"]), (w["x2"], w["y2"])]))
            for w in structured_walls
        ]
        door_tol = topo_thickness * 2.5 if topo_thickness > 0 else 80.0
        win_tol = topo_thickness * 1.5 if topo_thickness > 0 else 50.0
        for o, tol_o in [(d, door_tol) for d in doors] + [(w, win_tol) for w in windows]:
            # A PDF opening already validated at extraction carries its own proven
            # supporting_wall_id — trust that association (goal §4: require a valid
            # wall association) instead of re-deriving it here under a different
            # tolerance, which would spuriously flag a validated opening off-wall.
            if o.get("validation_status") == "VALID" and o.get("supporting_wall_id"):
                o["on_wall"], o["wall_id"] = True, o["supporting_wall_id"]
                continue
            try:
                pt = Point(*_opening_xy(o))
            except (TypeError, ValueError):
                o["on_wall"], o["wall_id"] = False, None
                continue
            wid, dist = None, math.inf
            for w_id, line in wall_lines:
                dd = line.distance(pt)
                if dd < dist:
                    wid, dist = w_id, dd
            o["on_wall"] = bool(dist <= tol_o)
            o["wall_id"] = wid if o["on_wall"] else None
            o["wall_distance_px"] = round(dist, 2)

    doors_by_room = _assign_openings(doors)
    windows_by_room = _assign_openings(windows)

    rooms: list[dict[str, Any]] = []
    for ridx, r in enumerate(resolved):
        label = r["label"]
        slug = r["slug"]
        items = r["items"]
        bbox = r["bbox"]
        boundary = r["boundary"]
        geom_source = r["geom_source"]
        assign_method = r["assign_method"]
        room_doors = doors_by_room.get(ridx, [])
        room_windows = windows_by_room.get(ridx, [])

        # Calculate metric dimensions
        width_m = round(bbox[2] * mpp, 2)
        depth_m = round(bbox[3] * mpp, 2)
        height_m = 2.7
        # Spec §7C: for a real architectural boundary use the ACTUAL polygon area,
        # not bbox width×depth (which overstates a non-rectangular room). Fall back
        # to the bbox estimate for furniture-derived rooms.
        is_architectural = str(geom_source).startswith("architectural")
        if is_architectural and boundary and len(boundary) >= 4:
            try:
                area_sqm = round(Polygon(boundary).area * mpp * mpp, 1)
            except Exception:  # noqa: BLE001
                area_sqm = round(width_m * depth_m, 1)
        else:
            area_sqm = round(width_m * depth_m, 1)

        # Truthful geometry state (items 11/12): a boundary proven from source
        # walls is CONFIRMED; a furniture-derived fallback boundary is UNCERTAIN
        # (never silently presented as architectural truth).
        validation_status = "CONFIRMED" if is_architectural else "UNCERTAIN"

        # Enrich furniture items with normalized room coordinates, stable identity, and room_id
        rw, rh = bbox[2], bbox[3]
        room_furniture = []
        for idx, it in enumerate(items):
            item_data = dict(it)
            item_data["id"] = it.get("uid") or f"{slug}_{idx+1}"
            item_data["type"] = it.get("item_id")
            item_data["room_id"] = slug
            item_data["room_assignment_method"] = assign_method
            item_data["normalized_x"] = round((float(it["cx"]) - bbox[0]) / (rw or 1.0), 3)
            item_data["normalized_y"] = round((float(it["cy"]) - bbox[1]) / (rh or 1.0), 3)
            item_data["name"] = it.get("name") or furniture_catalog.describe(str(it["item_id"]))[0]
            item_data["fixed"] = True
            room_furniture.append(item_data)

        rooms.append(
            {
                "id": slug,
                "label": label,
                "room_type": label,
                "bbox": bbox,
                "boundary": boundary,
                "width": bbox[2],
                "height": bbox[3],
                "dimensions": {
                    "width_m": width_m,
                    "depth_m": depth_m,
                    "height_m": height_m,
                    "area_sqm": area_sqm,
                },
                "geom_source": geom_source,
                "geometry_source": geom_source,
                "validation_status": validation_status,
                "supporting_wall_ids": r.get("supporting_wall_ids", []),
                "assign_method": assign_method,
                "room_assignment_method": assign_method,
                "doors": room_doors,
                "windows": room_windows,
                "furniture_count": len(room_furniture),
                "furniture": room_furniture,
            }
        )

    return rooms

