"""Authoritative door/window wall placement (deterministic).

scene_service attaches room.opening_placements: each rendered opening PROJECTED onto
its real supporting wall (structured geometry, via supporting_wall_id or a
geometry-constrained association) — NOT the furniture-bbox room boundary. The
frontend renders windows from these on-wall positions.

These tests prove: verified placements sit ON their named structured wall
(perpendicular drift removed), the along-wall position is within the wall segment,
Bedroom 1's window lands on the real left wall (not the furniture bbox / not raw),
and furniture is untouched.
"""

import math

from app.services import floor_plan_service, scene_service

FID = "f6b65d2b-4f96-4931-9f08-67dbd09776f6"


def _scene():
    return scene_service.build_scene(FID)


def _wall_by_id(scene, wid):
    return next((w for w in scene.get("structured_walls", []) if w.get("id") == wid), None)


def _perp(px, py, w):
    x1, y1, x2, y2 = w["x1"], w["y1"], w["x2"], w["y2"]
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy or 1.0
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def test_every_verified_window_sits_on_its_named_wall():
    scene = _scene()
    checked = 0
    for r in scene["rooms"]:
        for p in r.get("opening_placements", []):
            if p["kind"] != "window" or not p["verified"]:
                continue
            w = _wall_by_id(scene, p["wall_id"])
            assert w is not None, f"missing wall {p['wall_id']}"
            # projected placement lies ON the structured wall (perp ≈ 0)
            assert _perp(p["cx"], p["cy"], w) < 0.5
            # within the wall segment
            assert 0.0 <= p["wall_relative"]["normalized"] <= 1.0
            checked += 1
    assert checked > 0


def test_every_verified_door_sits_on_its_named_wall():
    scene = _scene()
    checked = 0
    for r in scene["rooms"]:
        for p in r.get("opening_placements", []):
            if p["kind"] != "door" or not p["verified"]:
                continue
            w = _wall_by_id(scene, p["wall_id"])
            assert w is not None, f"missing wall {p['wall_id']}"
            assert _perp(p["cx"], p["cy"], w) < 0.5          # ON the wall
            assert 0.0 <= p["wall_relative"]["normalized"] <= 1.0
            checked += 1
    assert checked > 0


def test_door_rotation_matches_its_wall_direction():
    scene = _scene()
    for r in scene["rooms"]:
        for p in r.get("opening_placements", []):
            if p["kind"] != "door" or not p["verified"]:
                continue
            wall_ang = float(p["wall_angle_deg"]) % 180
            drot = abs((float(p["rotation"]) % 180) - wall_ang)
            drot = min(drot, 180 - drot)
            assert drot <= 25, f"door rotation {p['rotation']} vs wall {wall_ang}"


def test_bedroom1_window_on_real_left_wall_not_bbox():
    scene = _scene()
    br1 = next(r for r in scene["rooms"] if "Bedroom 1" in r["label"])
    win = next(p for p in br1["opening_placements"] if p["kind"] == "window")
    assert win["verified"] is True
    assert win["wall_id"] is not None  # e.g. wall_086 (real left wall)
    bbox_left = min(p[0] for p in br1["boundary"])
    # NOT snapped to the furniture-bbox left edge…
    assert abs(win["cx"] - bbox_left) > 5
    # …on the real wall (perp ≈ 0 to its structured wall)…
    assert _perp(win["cx"], win["cy"], _wall_by_id(scene, win["wall_id"])) < 0.5
    # …at the authored height (along-wall position preserved).
    raw = next(f for f in br1["furniture"] if "window" in str(f["item_id"]))
    assert abs(win["cy"] - float(raw["cy"])) < 30


def test_unverifiable_openings_keep_authored_position_flagged():
    scene = _scene()
    for r in scene["rooms"]:
        for p in r.get("opening_placements", []):
            if not p["verified"]:
                assert p["wall_id"] is None  # honestly flagged, not invented


def test_furniture_unchanged_by_placement():
    canonical = floor_plan_service.get_canonical(FID)
    scene = _scene()
    canon = {str(f["uid"]): f for f in canonical["furniture"]}
    scene_furn = [f for r in scene["rooms"] for f in r["furniture"]]
    assert len(scene_furn) == len(canon) == 33
    for f in scene_furn:
        c = canon[str(f["uid"])]
        for k in ("cx", "cy", "w", "h", "rotation"):
            assert float(f[k]) == float(c[k])  # openings placement never moved furniture


def test_placements_cover_every_rendered_opening():
    scene = _scene()
    for r in scene["rooms"]:
        n_editor = sum(
            1 for f in r["furniture"]
            if "window" in str(f["item_id"]) or "door" in str(f["item_id"])
        )
        n_supp = len(r.get("supplemental_doors") or []) + len(r.get("supplemental_windows") or [])
        assert len(r.get("opening_placements", [])) == n_editor + n_supp
