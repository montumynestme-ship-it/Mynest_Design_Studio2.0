"""Phase 3 — deterministic door/window placement fidelity (drift-proof, synthetic).

Locks the honest wall-association behavior of ``scene_service`` directly, with
hand-built walls/openings so the assertions do NOT depend on the live plan (no
live-data drift). It exercises the REAL placement code
(``scene_service._attach_opening_placements`` / ``_find_supporting_wall``):

  * an opening that confidently associates to a wall is PROJECTED onto it
    (perpendicular drift removed, ``verified=True`` / ``status="PLACED"``);
  * an opening that is rotationally inconsistent with the only nearby wall,
    projects off a segment END, or is far from every wall is kept at its AUTHORED
    position (``verified=False`` / ``status="NEEDS_REVIEW"`` / ``wall_id=None``) —
    never relocated, snapped, or invented (the task's "keep unverified, don't guess").

Two of the cases reproduce the live unverified openings diagnosed in Phase 3:
a door authored perpendicular to its only nearby wall, and an opening projecting off
a short segment's end.

It also REUSES the existing ``validation_service.validate_2d_to_3d`` comparator
(not a duplicate) to prove detection of MOVED / REORIENTED / RESIZED / WALL-changed /
MISSING openings, and that opening placement never mutates furniture transforms.
"""

from app.services import scene_service, validation_service


def _wall(wid, x1, y1, x2, y2):
    return {"id": wid, "x1": float(x1), "y1": float(y1), "x2": float(x2), "y2": float(y2)}


def _open(uid, item_id, cx, cy, w, h, rot):
    return {"uid": uid, "item_id": item_id, "cx": cx, "cy": cy, "w": w, "h": h, "rotation": rot}


H1 = _wall("H1", 0, 100, 400, 100)    # horizontal wall, x 0..400 @ y=100
V1 = _wall("V1", 500, 0, 500, 400)    # vertical wall,   y 0..400 @ x=500
HS = _wall("HS", 0, 600, 50, 600)     # SHORT horizontal segment, x 0..50 @ y=600
WALLS = [H1, V1, HS]


def _place(openings):
    rooms = [{"furniture": list(openings)}]
    scene_service._attach_opening_placements(rooms, WALLS)
    return {p["id"]: p for p in rooms[0]["opening_placements"]}


def test_window_on_horizontal_wall_is_projected_and_verified():
    p = _place([_open("win-h", "window", 200, 110, 120, 20, 0.0)])  # 10px below H1, aligned
    w = p["win-h"]
    assert w["verified"] is True and w["status"] == "PLACED" and w["wall_id"] == "H1"
    assert abs(w["cy"] - 100.0) < 0.5 and abs(w["cx"] - 200.0) < 0.5  # projected onto the wall
    assert w["wall_relative"]["perp_removed_px"] > 0
    assert 0.0 <= w["wall_relative"]["normalized"] <= 1.0


def test_door_on_vertical_wall_is_projected_and_verified():
    p = _place([_open("door-v", "door", 480, 200, 90, 90, 90.0)])  # 20px from V1, rot aligned
    d = p["door-v"]
    assert d["verified"] is True and d["wall_id"] == "V1"
    assert abs(d["cx"] - 500.0) < 0.5  # snapped onto the vertical wall


def test_window_far_from_every_wall_kept_unverified_not_relocated():
    p = _place([_open("win-far", "window", 1000, 1000, 120, 20, 0.0)])
    w = p["win-far"]
    assert w["verified"] is False and w["status"] == "NEEDS_REVIEW" and w["wall_id"] is None
    assert w["cx"] == 1000 and w["cy"] == 1000  # authored position preserved (not relocated)


def test_door_perpendicular_to_only_near_wall_is_not_force_attached():
    # Reproduces live door-1791697527072: ~10px from a vertical wall but authored rot=0
    # (perpendicular). The rotation disagreement must keep it unverified — NOT snapped to
    # that wall (snapping would be guessing the user meant to rotate it).
    p = _place([_open("door-perp", "door", 490, 200, 90, 90, 0.0)])
    d = p["door-perp"]
    assert d["verified"] is False and d["wall_id"] is None and d["status"] == "NEEDS_REVIEW"
    assert d["cx"] == 490  # never snapped to the vertical wall at x=500


def test_opening_off_a_segment_end_kept_unverified():
    # Reproduces live door-1789215945981: rotation-aligned to a horizontal segment but
    # projecting beyond its end -> not attached (no off-end extrapolation / guess).
    p = _place([_open("win-offend", "window", 300, 600, 120, 20, 0.0)])  # HS spans only x 0..50
    w = p["win-offend"]
    assert w["verified"] is False and w["wall_id"] is None
    assert w["cx"] == 300 and w["cy"] == 600  # authored position preserved


def test_placement_never_mutates_furniture_transforms():
    bed = {"uid": "bed-1", "item_id": "bed", "cx": 250, "cy": 250, "w": 180, "h": 200, "rotation": 15}
    rooms = [{"furniture": [bed, _open("win-h", "window", 200, 110, 120, 20, 0.0)]}]
    scene_service._attach_opening_placements(rooms, WALLS)
    same = next(f for f in rooms[0]["furniture"] if f["uid"] == "bed-1")
    for k in ("cx", "cy", "w", "h", "rotation"):
        assert same[k] == bed[k]  # furniture untouched (relative; no hardcoded count)


def _cats(result):
    return {m["category"] for m in result["mismatches"]}


def test_reuse_validate_2d_to_3d_detects_moved_reoriented_resized_openings():
    base = {"id": "d1", "wall_id": "H1", "offset": 100.0, "w": 90.0, "h": 90.0, "rotation": 0.0}
    expected = {"doors": [base]}
    assert "DOOR_MOVED" in _cats(
        validation_service.validate_2d_to_3d(expected, {"doors": [{**base, "offset": 180.0}]}))
    assert "DOOR_REORIENTED" in _cats(
        validation_service.validate_2d_to_3d(expected, {"doors": [{**base, "rotation": 90.0}]}))
    assert "DOOR_RESIZED" in _cats(
        validation_service.validate_2d_to_3d(expected, {"doors": [{**base, "w": 130.0}]}))
    assert "DOOR_WALL_CHANGED" in _cats(
        validation_service.validate_2d_to_3d(expected, {"doors": [{**base, "wall_id": "V1"}]}))
    assert "DOOR_MISSING" in _cats(
        validation_service.validate_2d_to_3d(expected, {"doors": []}))


def test_reuse_validate_2d_to_3d_passes_identical_openings():
    base = {"id": "w1", "wall_id": "H1", "offset": 50.0, "w": 120.0, "h": 20.0, "rotation": 0.0}
    res = validation_service.validate_2d_to_3d({"windows": [base]}, {"windows": [dict(base)]})
    assert [m for m in res["mismatches"] if m["category"].startswith("WINDOW")] == []
