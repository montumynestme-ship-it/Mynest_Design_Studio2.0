"""Real-PDF wall/opening extraction + topology reconstruction (deterministic).

Guards the fix where wall geometry drawn as PDF path/curve primitives was lost
because the extractor read only page.lines. Doors (gold) and windows (cyan) must
be captured as OPENINGS, never as solid walls.
"""

import math

from app.services import architectural_service as arch
from app.services import floor_plan_service as fps
from app.services import geometry_extraction_service as ges
from app.services import room_reconstruction_raster, scene_service
from app.services import wall_reconstruction as wr

FID = "f6b65d2b-4f96-4931-9f08-67dbd09776f6"


def _geom():
    path, _, _ = fps.get_floor_plan_file(FID)
    return ges.extract_walls(str(path))


def test_extraction_captures_curve_primitive_walls() -> None:
    geom = _geom()
    sources = {w.get("source") for w in geom["structured_walls"]}
    # Straight lines AND the axis-aligned sub-segments of path/curve primitives.
    assert "line" in sources
    assert "curve_edge" in sources, "wall geometry drawn as curves must be captured"
    # Materially more than the old line-only reader (126) once curves are kept.
    assert len(geom["walls"]) >= 170


def test_doors_and_windows_are_openings_not_walls() -> None:
    geom = _geom()
    # Gold/cyan opening colours must never appear as structural walls.
    for c in geom["wall_colors"]:
        assert c not in ges._DOOR_HEXES and c not in ges._WINDOW_HEXES
    openings = geom["openings"]
    kinds = {o["kind"] for o in openings}
    assert "door" in kinds and "window" in kinds
    assert all(o["source"] == "pdf_rect" for o in openings)


def test_vector_topology_improves_with_complete_walls() -> None:
    geom = _geom()
    raw = [tuple(map(float, w[:4])) for w in geom["walls"]
           if math.hypot(w[2] - w[0], w[3] - w[1]) > 0]
    recon = wr.reconstruct_rooms_topology(raw)
    # Every confirmed room carries wall provenance + proven corners (no fabrication).
    for r in recon["rooms"]:
        assert r["supporting_wall_ids"], "confirmed room must map to source walls"
        assert r["corner_junction_ids"], "confirmed room corners must be proven junctions"
        assert r["min_edge_coverage"] >= 0.9
    # Capturing curve walls proves strictly more than the line-only baseline (1).
    assert recon["stats"]["confirmed"] >= 2


def test_scene_confirmed_rooms_match_pure_pdf_reconstruction() -> None:
    """CONFIRMED rooms come ONLY from the raster reconstruction bridged with the
    PDF's own validated openings — never inflated by furniture-named doorways. The
    scene's CONFIRMED count must equal the pure-PDF wall-enclosed region count."""
    geom = _geom()
    walls = geom["walls"]
    segs = [tuple(map(float, w[:4])) for w in walls
            if math.hypot(w[2] - w[0], w[3] - w[1]) > 0]
    thickness = wr.measure_tolerances(segs)["thickness"]
    path, _, _ = fps.get_floor_plan_file(FID)
    bridge = scene_service.select_bridge_openings(geom["openings"], [])
    proven = room_reconstruction_raster.reconstruct_rooms_raster(
        str(path), walls, bridge, thickness)["rooms"]

    scene = scene_service.build_scene(FID)
    confirmed = [r for r in scene["rooms"] if r.get("validation_status") == "CONFIRMED"]
    assert len(confirmed) == len(proven), "CONFIRMED rooms must equal pure-PDF regions"
    assert len(confirmed) >= 1
    for r in confirmed:
        assert str(r["geometry_source"]).startswith("architectural")
        assert r.get("supporting_wall_ids"), "confirmed room needs wall provenance"
    # Furniture is preserved exactly and assigned only to reconstructed rooms.
    scene_uids = sorted(str(f.get("uid") or f.get("id"))
                        for r in scene["rooms"] for f in r["furniture"])
    canon_uids = sorted(str(f.get("uid")) for f in fps.get_canonical(FID)["furniture"])
    assert scene_uids == canon_uids


# --- Opening schema + coordinate-system consistency (this goal) ---------------

_OPENING_KEYS = {"id", "kind", "cx", "cy", "w", "h", "rotation", "supporting_wall_id", "source"}


def test_openings_use_one_normalized_schema() -> None:
    geom = _geom()
    openings = geom["openings"]
    assert openings, "PDF has door/window rects → openings must be extracted"
    wall_ids = {w["id"] for w in geom["structured_walls"]}
    for o in openings:
        assert _OPENING_KEYS.issubset(o.keys()), f"missing keys: {o}"
        # cx/cy is the ONLY centre schema — no x/y-vs-cx/cy mismatch.
        assert "x" not in o and "y" not in o, f"opening still uses x/y: {o}"
        assert o["kind"] in ("door", "window")
        assert o["source"] == "pdf_rect"
        assert isinstance(o["cx"], (int | float)) and isinstance(o["cy"], (int | float))
        assert o["rotation"] in (0.0, 90.0)
        if not o["uncertain"]:
            assert o["supporting_wall_id"] in wall_ids, "linked wall must exist"
        else:
            assert o["uncertain_reason"], "uncertain opening must give a reason"


def test_opening_coordinate_conversion_matches_walls() -> None:
    """Openings must be in the SAME world coordinate system as walls (world = pt *
    WORLD_SCALE), verified against the raw pdfplumber rect centres."""
    import pdfplumber
    path, _, _ = fps.get_floor_plan_file(FID)
    geom = ges.extract_walls(str(path))
    scale = ges.WORLD_SCALE
    with pdfplumber.open(str(path)) as pdf:
        rect_centres = []
        for r in pdf.pages[0].rects:
            hexc = ges._stroke_hex(r.get("stroking_color"))
            if hexc in ges._DOOR_HEXES or hexc in ges._WINDOW_HEXES:
                rect_centres.append(((r["x0"] + r["x1"]) / 2 * scale,
                                     (r["top"] + r["bottom"]) / 2 * scale))
    pw = geom["page"]["width"]
    for o in geom["openings"]:
        # each opening centre equals some source rect centre (× scale), in world px
        assert any(abs(o["cx"] - rcx) < 0.5 and abs(o["cy"] - rcy) < 0.5
                   for rcx, rcy in rect_centres), f"opening not from a source rect: {o}"
        assert 0 <= o["cx"] <= pw, "opening cx must be within the page (world px)"


def test_scene_doors_windows_are_pdf_sourced_cxcy() -> None:
    scene = scene_service.build_scene(FID)
    openings = [o for r in scene["rooms"] for o in (r["doors"] + r["windows"])]
    assert openings
    for o in openings:
        assert "cx" in o and "cy" in o and "x" not in o
        assert o.get("source") == "pdf_rect"
        assert o.get("kind") in ("door", "window")


def test_no_furniture_named_openings_leak_into_walls() -> None:
    geom = _geom()
    # Gold(door)/cyan(window) colours must never appear in the wall set.
    for c in geom["wall_colors"]:
        assert c not in ges._DOOR_HEXES and c not in ges._WINDOW_HEXES


# --- Goal §6: bridging source, validation, and strict assignment --------------

def _proven_room(poly, wall_ids=("wall_001",)):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return {
        "polygon": list(poly),
        "bbox": [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)],
        "wall_supported": True,
        "supporting_wall_ids": list(wall_ids),
    }


def test_bridge_uses_validated_pdf_openings_not_furniture() -> None:
    """When PDF openings exist, ONLY validated PDF openings bridge — never canonical
    door/window furniture (goal §1/§2)."""
    pdf_openings = [
        {"id": "door_001", "kind": "door", "cx": 10, "cy": 10, "w": 8, "h": 4,
         "validation_status": "VALID", "uncertain": False, "source": "pdf_rect"},
    ]
    furniture = [{"uid": "f1", "item_id": "door-wooden", "cx": 99, "cy": 99, "w": 8, "h": 4}]
    bridge = scene_service.select_bridge_openings(pdf_openings, furniture)
    assert [o["id"] for o in bridge] == ["door_001"]
    assert all(o.get("source") == "pdf_rect" for o in bridge)
    assert not any(str(o.get("item_id", "")).startswith("door") for o in bridge)


def test_bridge_falls_back_to_furniture_only_without_pdf_openings() -> None:
    furniture = [
        {"uid": "f1", "item_id": "door-wooden", "cx": 1, "cy": 1, "w": 8, "h": 4},
        {"uid": "f2", "item_id": "sofa-3seat", "cx": 5, "cy": 5, "w": 8, "h": 4},
    ]
    bridge = scene_service.select_bridge_openings([], furniture)
    assert [o["uid"] for o in bridge] == ["f1"]  # only the door furniture, no sofa


def test_invalid_and_uncertain_openings_never_bridged() -> None:
    pdf_openings = [
        {"id": "d_ok", "kind": "door", "validation_status": "VALID", "uncertain": False},
        {"id": "d_unc", "kind": "door", "validation_status": "UNCERTAIN", "uncertain": True},
        {"id": "d_bad", "kind": "window", "validation_status": "INVALID", "uncertain": True},
    ]
    bridge = scene_service.select_bridge_openings(pdf_openings, [])
    assert [o["id"] for o in bridge] == ["d_ok"]


def test_extracted_openings_carry_validation_status() -> None:
    geom = _geom()
    for o in geom["openings"]:
        assert o["validation_status"] in ("VALID", "UNCERTAIN", "INVALID")
        # A VALID opening must have numeric dims and a real supporting wall.
        if o["validation_status"] == "VALID":
            assert o["w"] > 0 and o["h"] > 0
            assert o["supporting_wall_id"] is not None
        else:
            assert o["uncertain"] and o["uncertain_reason"]


def test_invalid_opening_near_wall_not_bridged() -> None:
    """An opening whose CENTRE is near a wall but whose FOOTPRINT lies beside it
    (does not cross the wall) is UNCERTAIN and never bridged (goal §2)."""
    wall = {"id": "wall_001", "x1": 0.0, "y1": 100.0, "x2": 400.0, "y2": 100.0,
            "angle_deg": 0.0}
    # PDF-pt rect → ×scale(2): world centre (100,150), w40 h20. Centre 50px from the
    # wall (within link_tol) but footprint (y 140..160) is 40px off it > band(15).
    rects = [(40.0, 70.0, 60.0, 80.0, ges._DOOR_HEXES[0])]
    ops = ges._extract_openings(rects, [wall], ges.WORLD_SCALE, (0, 0, 10000, 10000), 0.0)
    assert len(ops) == 1
    assert ops[0]["validation_status"] == "UNCERTAIN"
    assert "cross" in (ops[0]["uncertain_reason"] or "")
    assert scene_service.select_bridge_openings(ops, []) == []


def test_valid_opening_crossing_wall_is_bridged() -> None:
    """An opening whose footprint crosses its supporting wall is VALID and bridged."""
    wall = {"id": "wall_001", "x1": 0.0, "y1": 100.0, "x2": 400.0, "y2": 100.0,
            "angle_deg": 0.0}
    # world centre (100,100) ON the wall; footprint straddles the wall line.
    rects = [(40.0, 45.0, 60.0, 55.0, ges._DOOR_HEXES[0])]
    ops = ges._extract_openings(rects, [wall], ges.WORLD_SCALE, (0, 0, 10000, 10000), 0.0)
    assert ops[0]["validation_status"] == "VALID"
    assert ops[0]["supporting_wall_id"] == "wall_001"
    assert scene_service.select_bridge_openings(ops, []) == ops


def test_opening_xy_normalizes_x_y_to_cx_cy() -> None:
    assert arch._opening_xy({"cx": 12.0, "cy": 34.0}) == (12.0, 34.0)
    # legacy x/y is accepted as a fallback so no x/y-vs-cx/cy mismatch reappears
    assert arch._opening_xy({"x": 5.0, "y": 6.0}) == (5.0, 6.0)


def test_furniture_outside_proven_room_stays_uncertain() -> None:
    """A furniture centre inside no proven polygon is kept UNCERTAIN, never moved
    into another room, and its coordinates are never altered (goal §3)."""
    proven = [_proven_room([(0, 0), (200, 0), (200, 200), (0, 200), (0, 0)])]
    furniture = [
        {"uid": "inside", "item_id": "bed-king", "cx": 100, "cy": 100, "w": 40, "h": 40},
        {"uid": "outside", "item_id": "sofa-3seat", "cx": 900, "cy": 900, "w": 40, "h": 40},
    ]
    rooms = arch.reconstruct_rooms(furniture, [], doors=[], windows=[], proven_rooms=proven)
    by_status: dict[str, list[str]] = {}
    for r in rooms:
        for f in r["furniture"]:
            by_status.setdefault(r["validation_status"], []).append(f["uid"])
    assert "inside" in by_status.get("CONFIRMED", [])
    assert "outside" in by_status.get("UNCERTAIN", [])
    # Coordinates preserved exactly.
    scene_items = {f["uid"]: f for r in rooms for f in r["furniture"]}
    assert scene_items["outside"]["cx"] == 900 and scene_items["outside"]["cy"] == 900


def test_no_broad_nearest_room_reassignment() -> None:
    """An item just outside a proven room (within the OLD nearest-room tolerance)
    must NOT be absorbed into it — strict containment only (goal §3)."""
    proven = [_proven_room([(0, 0), (200, 0), (200, 200), (0, 200), (0, 0)])]
    # cx=260 is 60px outside the right wall — the removed near_tol would have pulled
    # it in; strict containment must leave it UNCERTAIN.
    furniture = [{"uid": "near", "item_id": "console-slim", "cx": 260, "cy": 100,
                  "w": 20, "h": 20}]
    rooms = arch.reconstruct_rooms(furniture, [], doors=[], windows=[], proven_rooms=proven)
    conf = [f["uid"] for r in rooms if r["validation_status"] == "CONFIRMED"
            for f in r["furniture"]]
    assert "near" not in conf, "near-wall item must not be reassigned into the room"


def test_open_plan_singleton_sections_both_preserved_in_label() -> None:
    """Open-plan root-cause regression: ONE wall-proven polygon containing furniture
    from two sections with exactly one item each (e.g. chimney->Kitchen=1 +
    dining-table->Dining Area=1) must keep BOTH section labels ("Kitchen & Dining
    Area"), not silently drop the minority/tied one. This guards `_majority`'s
    inclusion threshold against the top==1 case where a floor of 2 cleared NO section.
    Generic: no label/plan/coordinate special-casing — driven only by contained
    furniture evidence."""
    proven = [_proven_room([(0, 0), (400, 0), (400, 400), (0, 400), (0, 0)])]
    furniture = [
        {"uid": "k1", "item_id": "chimney", "cx": 120, "cy": 120, "w": 20, "h": 20},
        {"uid": "d1", "item_id": "dining-table", "cx": 280, "cy": 280, "w": 20, "h": 20},
    ]
    rooms = arch.reconstruct_rooms(furniture, [], doors=[], windows=[], proven_rooms=proven)
    conf = [r for r in rooms if r["validation_status"] == "CONFIRMED"]
    assert len(conf) == 1, "exactly one wall-proven room for the single polygon"
    label = conf[0]["label"]
    assert "Kitchen" in label and "Dining Area" in label, f"both sections kept, got {label!r}"
    assert "&" in label, f"open-plan co-label must be '&'-joined for the faithful split, got {label!r}"
    # Both contained items stay in that one room; coordinates untouched.
    uids = sorted(f["uid"] for f in conf[0]["furniture"])
    assert uids == ["d1", "k1"]
    byuid = {f["uid"]: f for f in conf[0]["furniture"]}
    assert (byuid["k1"]["cx"], byuid["k1"]["cy"]) == (120, 120)
    assert (byuid["d1"]["cx"], byuid["d1"]["cy"]) == (280, 280)


def test_single_section_proven_room_label_unchanged() -> None:
    """Invariant: the fix must NOT turn an ordinary single-section room into a shared
    label. A polygon containing only Kitchen items stays "Kitchen"."""
    proven = [_proven_room([(0, 0), (400, 0), (400, 400), (0, 400), (0, 0)])]
    furniture = [
        {"uid": "k1", "item_id": "chimney", "cx": 120, "cy": 120, "w": 20, "h": 20},
        {"uid": "k2", "item_id": "kitchen-base", "cx": 280, "cy": 280, "w": 20, "h": 20},
    ]
    rooms = arch.reconstruct_rooms(furniture, [], doors=[], windows=[], proven_rooms=proven)
    conf = [r for r in rooms if r["validation_status"] == "CONFIRMED"]
    assert len(conf) == 1 and conf[0]["label"] == "Kitchen"


def test_windows_outside_polygon_confirmed_only_by_wall_ownership() -> None:
    """A window whose centre is outside every architectural room polygon (it sits IN
    the wall, so its centre is outside the eroded interior) is CONFIRMED ONLY when it
    is associated to that room by WALL-OWNERSHIP — its proven supporting wall is one
    of the room's supporting walls. Otherwise it stays UNCERTAIN. Never confirmed by
    bbox and never by nearest-room."""
    scene = scene_service.build_scene(FID)
    from shapely.geometry import Point, Polygon
    polys = {
        r["id"]: Polygon(r["boundary"])
        for r in scene["rooms"]
        if str(r["geometry_source"]).startswith("architectural") and len(r["boundary"]) >= 4
    }
    all_polys = list(polys.values())
    for r in scene["rooms"]:
        for w in r["windows"]:
            contained = any(p.covers(Point(w["cx"], w["cy"])) for p in all_polys)
            if contained:
                continue
            if w.get("validation_status") == "CONFIRMED":
                # only legitimate via wall-ownership of THIS room's wall
                assert w.get("assignment") == "wall_owned"
                assert w.get("wall_id") in (r.get("supporting_wall_ids") or [])
            else:
                assert w.get("validation_status") == "UNCERTAIN"


def test_geometry_invalid_true_when_not_faithful() -> None:
    scene = scene_service.build_scene(FID)
    faithful = scene["geometry_validation"]["geometry_faithful"]
    assert scene["geometry_invalid"] is (not faithful)
    assert scene["validation_status"] == (
        "GEOMETRY_FAITHFUL" if faithful else "GEOMETRY_MISMATCH")


def test_all_canonical_furniture_unchanged_in_scene() -> None:
    scene = scene_service.build_scene(FID)
    canon = {str(f["uid"]): f for f in fps.get_canonical(FID)["furniture"]}
    scene_items = {str(f.get("uid") or f.get("id")): f
                   for r in scene["rooms"] for f in r["furniture"]}
    assert set(scene_items) == set(canon), "every canonical item present, none added"
    for uid, c in canon.items():
        s = scene_items[uid]
        for attr in ("cx", "cy", "w", "h"):
            assert abs(float(c[attr]) - float(s[attr])) < 1e-6, f"{uid}.{attr} changed"
        assert str(c["item_id"]) == str(s.get("item_id") or s.get("type"))
        assert abs(float(c.get("rotation", 0)) - float(s.get("rotation", 0))) < 1e-6


def test_openings_associated_to_rooms_by_wall_ownership() -> None:
    """Wall-ownership association: validated openings and wall-embedded furniture
    symbols are attached to the proven room whose wall they sit on (not nearest-room),
    so windows compose into the proven rooms' base images. Room LABELS are preserved
    (a wall-owned symbol never flips a room's identity) and furniture stays exact."""
    scene = scene_service.build_scene(FID)
    confirmed = [r for r in scene["rooms"] if r.get("validation_status") == "CONFIRMED"]
    labels = sorted(r["label"] for r in confirmed)
    # The five wall-proven rooms keep their real identities: a wall-owned SYMBOL never
    # relabels a room, but genuine open-plan furniture CONTAINED in the shared polygon
    # legitimately co-labels it. Here the dining-table sits inside the Kitchen wall cycle
    # (open-plan Kitchen+Dining, no wall between), so the proven room is "Kitchen & Dining
    # Area" — neither section is dropped. (Downstream _room_faithful_map splits on "&".)
    assert labels == ["Bedroom 1", "Bedroom 2", "Bedroom 3", "Kitchen & Dining Area", "Living Area"]
    # Windows now compose into proven rooms via wall-ownership (was 0 before).
    assert sum(len(r["windows"]) for r in confirmed) >= 3
    # Every wall-owned opening is tied to a wall the room actually owns.
    for r in confirmed:
        for o in r["doors"] + r["windows"]:
            if o.get("assignment") == "wall_owned":
                assert o.get("wall_id") in (r.get("supporting_wall_ids") or [])
    # Furniture preserved EXACTLY (count + identity), none created by association.
    scene_uids = sorted(str(f.get("uid") or f.get("id"))
                        for r in scene["rooms"] for f in r["furniture"])
    canon_uids = sorted(str(f.get("uid")) for f in fps.get_canonical(FID)["furniture"])
    assert scene_uids == canon_uids
