"""Extraction diagnostic report (spec §13/§14/§24) — per-room validation."""

from app.services import diagnostics_service as diag

# A single top wall segment for the 100x100 room used below.
_WALLS = [[0.0, 0.0, 100.0, 0.0], [0.0, 100.0, 100.0, 100.0]]


def _room(*, furniture, windows=(), source="architectural", bbox=(0.0, 0.0, 100.0, 100.0)):
    x0, y0, w, h = bbox
    return {
        "id": "bedroom-1",
        "label": "Bedroom 1",
        "geometry_source": source,
        "bbox": list(bbox),
        # A real architectural room always carries a closed boundary polygon.
        "boundary": [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h), (x0, y0)],
        "dimensions": {"width_m": 4.0, "depth_m": 4.0},
        "doors": [],
        "windows": list(windows),
        "furniture": list(furniture),
    }


def _bed(uid="b1", cx=50, cy=50, w=40, h=40, rot=0):
    return {"uid": uid, "item_id": "bed", "name": "Bed",
            "cx": cx, "cy": cy, "w": w, "h": h, "rotation": rot}


def test_valid_architectural_room_is_confirmed():
    win = {"id": "w1", "wall_id": "wall_001", "x": 50, "y": 0, "width": 30, "rotation_deg": 0}
    rep = diag._room_report(_room(furniture=[_bed()], windows=[win]), _WALLS)
    assert rep["status"] == "CONFIRMED"
    assert rep["furniture_count"] == 1
    assert rep["windows"][0]["on_wall"] is True
    assert rep["windows"][0]["inside_room"] is True


def test_window_off_wall_is_invalid():
    win = {"id": "w1", "wall_id": None, "x": 50, "y": 500, "width": 30, "rotation_deg": 0}
    rep = diag._room_report(_room(furniture=[_bed()], windows=[win]), _WALLS)
    assert rep["status"] == "WINDOW_GEOMETRY_INVALID"
    assert rep["windows"][0]["on_wall"] is False


def test_window_inside_bbox_but_outside_L_polygon_is_invalid():
    """Goal §3: for an architectural room the inside-room test is the real polygon,
    not the bbox. A window in an L-shaped room's notch is inside the bbox yet
    outside the polygon → WINDOW_GEOMETRY_INVALID."""
    # L-shaped room: full 100x100 bbox, but the top-right quadrant is a notch that
    # is OUTSIDE the polygon.
    l_poly = [(0, 0), (100, 0), (100, 50), (50, 50), (50, 100), (0, 100), (0, 0)]
    room = {
        "id": "living", "label": "Living", "geometry_source": "architectural",
        "bbox": [0.0, 0.0, 100.0, 100.0], "boundary": l_poly,
        "dimensions": {"width_m": 4.0, "depth_m": 4.0}, "doors": [],
        "windows": [{"id": "w1", "supporting_wall_id": "wall_x", "cx": 75, "cy": 75,
                     "w": 30, "h": 8, "rotation": 0, "on_wall": True}],
        "furniture": [_bed(cx=25, cy=25)],
    }
    walls = [[50.0, 75.0, 100.0, 75.0]]  # a wall through the notch → window on_wall
    rep = diag._room_report(room, walls)
    assert diag._in_bbox(75, 75, [0.0, 0.0, 100.0, 100.0]) is True  # inside the bbox
    assert rep["windows"][0]["inside_test"] == "polygon"  # authoritative test
    assert rep["windows"][0]["inside_room"] is False       # outside the real polygon
    assert rep["status"] == "WINDOW_GEOMETRY_INVALID"


def test_fallback_room_window_uses_bbox_context_and_stays_uncertain():
    """A furniture-fallback room uses the bbox as diagnostic context only (never
    authoritative) and remains UNCERTAIN regardless of the window (goal §3)."""
    win = {"id": "w1", "supporting_wall_id": "wall_001", "cx": 50, "cy": 0,
           "w": 30, "h": 8, "rotation": 0}
    rep = diag._room_report(
        _room(furniture=[_bed()], windows=[win], source="furniture_fallback"), _WALLS)
    assert rep["windows"][0]["inside_test"] == "bbox"
    assert rep["status"] == "UNCERTAIN"


def test_furniture_outside_room_is_invalid():
    rep = diag._room_report(_room(furniture=[_bed(cx=500, cy=500)]), _WALLS)
    assert rep["status"] == "EXTRACTION_INVALID"
    assert any("outside room boundary" in i for i in rep["issues"])


def test_duplicate_uid_and_near_identical_flagged():
    items = [_bed(uid="b1", cx=50, cy=50), _bed(uid="b1", cx=51, cy=50)]
    rep = diag._room_report(_room(furniture=items), _WALLS)
    assert rep["status"] == "EXTRACTION_INVALID"
    assert any("duplicate uid" in i for i in rep["issues"])
    assert any("near-identical" in i for i in rep["issues"])


def test_furniture_fallback_room_is_uncertain_not_confirmed():
    rep = diag._room_report(_room(furniture=[_bed()], source="furniture_fallback"), _WALLS)
    assert rep["status"] == "UNCERTAIN"


def test_non_positive_dimensions_flagged():
    rep = diag._room_report(_room(furniture=[_bed(w=0, h=40)]), _WALLS)
    assert rep["status"] == "EXTRACTION_INVALID"
    assert any("non-positive" in i for i in rep["issues"])


def test_wall_connectivity_closed_vs_fragmented():
    closed = [
        {"x1": 0, "y1": 0, "x2": 100, "y2": 0},
        {"x1": 100, "y1": 0, "x2": 100, "y2": 100},
        {"x1": 100, "y1": 100, "x2": 0, "y2": 100},
        {"x1": 0, "y1": 100, "x2": 0, "y2": 0},
    ]
    c = diag._wall_connectivity(closed)
    assert c["forms_closed_rooms"] is True
    assert c["isolated_endpoints_12px"] == 0
    # Disconnected segments far apart → no closed room, all endpoints isolated.
    frag = [
        {"x1": 0, "y1": 0, "x2": 50, "y2": 0},
        {"x1": 200, "y1": 200, "x2": 260, "y2": 200},
    ]
    f = diag._wall_connectivity(frag)
    assert f["forms_closed_rooms"] is False
    assert f["isolated_endpoints_12px"] == 4


def test_point_segment_distance_helpers():
    # Point on the segment → ~0; point one unit above the midpoint → ~1.
    assert diag._point_seg_dist(50, 0, 0, 0, 100, 0) == 0.0
    assert abs(diag._min_wall_dist(50, 1, _WALLS) - 1.0) < 1e-6
