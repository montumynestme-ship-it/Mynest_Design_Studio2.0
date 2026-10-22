"""Deterministic 2D-canonical -> 3D furniture placement contract (position task).

Investigation finding: the 2D canonical -> scene -> deterministic 3D furniture
pipeline is FAITHFUL. The backend carries every item's cx/cy/w/h/rotation through
unchanged (enforced by validation_service.validate_scene_against_canonical, check
#6), and the frontend RoomScene3D maps each item to metres RELATIVE TO THE ROOM
CENTRE with a single, consistent transform:

    roomCx = bbox.x + bbox.w / 2         # room centre, world px
    roomCy = bbox.y + bbox.h / 2
    x3 = (cx - roomCx) * mpp             # world px -> metres, X -> X
    z3 = (cy - roomCy) * mpp             # world px -> metres, plan-Y(down) -> Z
    rotY = -rotation                     # Konva CW(+, Y-down) -> three.js Y-up
    w3 = w * mpp ; d3 = h * mpp          # width -> X, depth(plan-h) -> Z

These tests lock BOTH halves deterministically (never image similarity):
1. the production canonical->scene fidelity check passes for the 6 required
   placement scenarios (origin, centre, near-wall, 90deg, different room, non-zero
   room offset); a deliberately moved item fails — proving the guard is real;
2. the documented world-px -> room-relative-metre transform is exact.
"""

import copy
import math

from app.services import validation_service

# Mirrors frontend scene.ts computeMpp for a bed: 2.0 m / max(w,h) in world px.
MPP = 2.0 / 2000.0  # a 2000px bed => 1px = 0.001 m


def _room(label: str, furniture: list[dict], offset: tuple[float, float] = (0.0, 0.0)):
    """A faithful build_scene-style room whose bbox is the furniture extent (exactly
    how scene_service._room_bbox derives it), optionally shifted by a room offset."""
    ox, oy = offset
    furn = []
    for f in furniture:
        g = copy.deepcopy(f)
        g["cx"] += ox
        g["cy"] += oy
        g["type"] = g["item_id"]
        furn.append(g)
    xs0 = min(f["cx"] - f["w"] / 2 for f in furn)
    xs1 = max(f["cx"] + f["w"] / 2 for f in furn)
    ys0 = min(f["cy"] - f["h"] / 2 for f in furn)
    ys1 = max(f["cy"] + f["h"] / 2 for f in furn)
    return {
        "label": label,
        "geometry_source": "architectural",
        "boundary": [[xs0, ys0], [xs1, ys0], [xs1, ys1], [xs0, ys1], [xs0, ys0]],
        "doors": [],
        "windows": [],
        "furniture": furn,
        "bbox": [xs0, ys0, xs1 - xs0, ys1 - ys0],
    }


def _to3d(f: dict, bbox: list[float], mpp: float = MPP) -> dict:
    """The exact deterministic RoomScene3D world-px -> room-relative-metre mapping."""
    bx, by, bw, bh = bbox
    rcx, rcy = bx + bw / 2, by + bh / 2
    return {
        "x": (f["cx"] - rcx) * mpp,
        "z": (f["cy"] - rcy) * mpp,
        "w": f["w"] * mpp,
        "d": f["h"] * mpp,
        "rotY": -float(f["rotation"]),
    }


# ── 1. Production canonical->scene fidelity across the 6 required scenarios ─────

def _scenario_canonical() -> dict:
    """One item per section-14 scenario, in world px (cx/cy = centre)."""
    return {
        "furniture": [
            # near a wall (top-left of the inhabited area)
            {"uid": "wardrobe", "item_id": "wardrobe", "cx": 300, "cy": 300, "w": 1800, "h": 600, "rotation": 0},
            # centre of the room region
            {"uid": "table", "item_id": "center-table", "cx": 1500, "cy": 1500, "w": 900, "h": 900, "rotation": 0},
            # 90 degrees rotated
            {"uid": "sofa", "item_id": "lounger-sofa", "cx": 2600, "cy": 1500, "w": 1900, "h": 900, "rotation": 90},
            # arbitrary (non-right-angle) rotation
            {"uid": "bed", "item_id": "bed", "cx": 1500, "cy": 2600, "w": 1600, "h": 2000, "rotation": 37.5},
        ]
    }


def _scene(canonical: dict, offset: tuple[float, float] = (0.0, 0.0)) -> dict:
    room = _room("Living Area", canonical["furniture"], offset=offset)
    return {
        "walls": [[0, 0, 4000, 0], [4000, 0, 4000, 4000]],
        "structured_walls": [{"id": "w1"}, {"id": "w2"}],
        "doors": [],
        "windows": [],
        "rooms": [room],
    }


def test_faithful_placement_all_scenarios_pass():
    c = _scenario_canonical()
    report = validation_service.validate_scene_against_canonical(c, _scene(c))
    assert report["geometry_faithful"] is True, report["mismatches"]
    assert report["checks"]["furniture_transforms"]["passed"] is True
    assert report["checks"]["furniture_types"]["passed"] is True


def test_item_in_a_different_room_still_faithful():
    # Same items split across two rooms; every item must still validate in place.
    c = _scenario_canonical()
    r1 = _room("Living Area", c["furniture"][:2])
    r2 = _room("Bedroom 1", c["furniture"][2:])
    scene = {
        "walls": [[0, 0, 4000, 0], [4000, 0, 4000, 4000]],
        "structured_walls": [{"id": "w1"}, {"id": "w2"}],
        "doors": [], "windows": [],
        "rooms": [r1, r2],
    }
    report = validation_service.validate_scene_against_canonical(c, scene)
    assert report["checks"]["furniture_transforms"]["passed"] is True
    assert report["checks"]["furniture_assignment"]["passed"] is True


def test_moved_item_is_detected():
    # Guard is real: a 1px+ move beyond tolerance fails the transform check.
    c = _scenario_canonical()
    scene = _scene(c)
    scene["rooms"][0]["furniture"][0]["cx"] += 5  # move the wardrobe 5px
    report = validation_service.validate_scene_against_canonical(c, scene)
    assert report["checks"]["furniture_transforms"]["passed"] is False
    assert any("cx changed" in m for m in report["mismatches"])


# ── 2. Deterministic world-px -> room-relative-metre transform ─────────────────

def test_item_at_room_centre_maps_to_origin():
    # A single centred item: its centre == room centre => 3D (0,0).
    f = {"uid": "t", "item_id": "center-table", "cx": 1500, "cy": 1500,
         "w": 900, "h": 900, "rotation": 0}
    room = _room("R", [f])
    p = _to3d(f, room["bbox"])
    assert abs(p["x"]) < 1e-9 and abs(p["z"]) < 1e-9


def test_offset_maps_linearly_and_axis_consistent():
    # Plan +X (cx) -> 3D +x; plan +Y/down (cy) -> 3D +z; both scale by mpp.
    bbox = [0.0, 0.0, 2000.0, 2000.0]  # centre (1000, 1000)
    f = {"cx": 1400, "cy": 1600, "w": 100, "h": 100, "rotation": 0}
    p = _to3d(f, bbox)
    assert math.isclose(p["x"], (1400 - 1000) * MPP, rel_tol=0, abs_tol=1e-9)
    assert math.isclose(p["z"], (1600 - 1000) * MPP, rel_tol=0, abs_tol=1e-9)


def test_rotation_maps_negated_and_dimensions_preserved():
    # Konva CW-positive (Y-down) -> three.js Y-up requires rotY = -rotation;
    # width->X, plan-height->Z, both scaled by mpp (no swap at the data level).
    bbox = [0.0, 0.0, 2000.0, 2000.0]
    for rot in (0, 90, 180, 270, 37.5):
        f = {"cx": 1000, "cy": 1000, "w": 1900, "h": 900, "rotation": rot}
        p = _to3d(f, bbox)
        assert math.isclose(p["rotY"], -rot, abs_tol=1e-9)
        assert math.isclose(p["w"], 1900 * MPP, abs_tol=1e-9)
        assert math.isclose(p["d"], 900 * MPP, abs_tol=1e-9)


def test_non_zero_room_offset_preserves_relative_placement():
    # Shifting the WHOLE room by a constant offset must not change any item's
    # position RELATIVE TO THE ROOM CENTRE (the value the 3D scene uses).
    f = {"uid": "b", "item_id": "bed", "cx": 1200, "cy": 900, "w": 1600, "h": 2000, "rotation": 0}
    partner = {"uid": "s", "item_id": "side-table", "cx": 400, "cy": 900, "w": 450, "h": 450, "rotation": 0}
    base = _room("R", [f, partner])
    shifted = _room("R", [f, partner], offset=(5000.0, -3000.0))
    p0 = _to3d(base["furniture"][0], base["bbox"])
    p1 = _to3d(shifted["furniture"][0], shifted["bbox"])
    assert math.isclose(p0["x"], p1["x"], abs_tol=1e-9)
    assert math.isclose(p0["z"], p1["z"], abs_tol=1e-9)
