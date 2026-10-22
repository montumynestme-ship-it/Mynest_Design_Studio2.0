"""Tests for the canonical-2D -> 3D furniture transform audit (STEP 2, audit only).

Verifies the transcribed production transform (RoomScene3D.tsx) numerically, and that
the real FID furniture transforms with zero divergence and intact invariants. No
production code is modified.
"""

import pytest

from app.services import floor_plan_service
from scripts.furniture_2d_to_3d_audit import actual_3d, build_audit, compute_mpp, expected_3d

FID = "f6b65d2b-4f96-4931-9f08-67dbd09776f6"
MPP = 0.01  # unit mpp-ish for simple synthetic checks (0.01 m/px)


def _f(cx, cy, w=100, h=50, rotation=0.0, item_id="bed", uid="u"):
    return {"cx": cx, "cy": cy, "w": w, "h": h, "rotation": rotation, "item_id": item_id, "uid": uid}


# 1. center item -> origin
def test_center_item_maps_to_origin():
    a = actual_3d(_f(500, 500), 500, 500, MPP)
    assert a["x"] == pytest.approx(0.0) and a["z"] == pytest.approx(0.0)


# 2. left of centre -> -x
def test_left_of_centre_negative_x():
    assert actual_3d(_f(400, 500), 500, 500, MPP)["x"] < 0


# 3. right of centre -> +x
def test_right_of_centre_positive_x():
    assert actual_3d(_f(600, 500), 500, 500, MPP)["x"] > 0


# 4. above centre (smaller cy) -> -z
def test_above_centre_negative_z():
    assert actual_3d(_f(500, 400), 500, 500, MPP)["z"] < 0


# 5. below centre (larger cy) -> +z
def test_below_centre_positive_z():
    assert actual_3d(_f(500, 600), 500, 500, MPP)["z"] > 0


# 6. rotation negated (Y-down -> Z handedness), no double/90 rotation
def test_rotation_negated():
    assert actual_3d(_f(500, 500, rotation=30), 500, 500, MPP)["rotation_y_deg"] == pytest.approx(-30.0)
    assert actual_3d(_f(500, 500, rotation=-90), 500, 500, MPP)["rotation_y_deg"] == pytest.approx(90.0)


# 7. width->width, height->depth (NO swap)
def test_width_depth_no_swap():
    a = actual_3d(_f(0, 0, w=180, h=40), 0, 0, 1.0)
    assert a["width"] == pytest.approx(180.0) and a["depth"] == pytest.approx(40.0)


# 8. 2D Y maps to 3D Z, never to 3D Y (y stays 0)
def test_y_is_floor_not_plan_y():
    a = actual_3d(_f(500, 900), 500, 500, MPP)
    assert a["y"] == 0.0 and a["z"] != 0.0


# 9. expected == actual (no divergence) for a normal-size item
def test_expected_equals_actual_no_divergence():
    f = _f(640, 710, w=180, h=90, rotation=15)
    e, a = expected_3d(f, 500, 500, MPP), actual_3d(f, 500, 500, MPP)
    for k in ("x", "z", "width", "depth", "rotation_y_deg"):
        assert e[k] == pytest.approx(a[k])


# 10. compute_mpp prefers a bed
def test_compute_mpp_prefers_bed():
    rooms = [{"furniture": [{"item_id": "bed", "w": 100, "h": 200}]}]
    assert compute_mpp(rooms) == pytest.approx(2.0 / 200)


# ── REAL FID audit: zero divergence, room association + invariants intact ────────
def test_fid_audit_zero_divergence_and_invariants():
    audit = build_audit(FID)
    assert audit["design_version_id"] and audit["furniture_count"] >= 1
    canonical = floor_plan_service.get_canonical(FID)
    canon_non_opening = [c for c in canonical["furniture"]
                         if "door" not in str(c["item_id"]) and "window" not in str(c["item_id"])]
    # furniture count (non-opening) preserved into the scene transform
    assert audit["furniture_count"] == len(canon_non_opening)
    for it in audit["items"]:
        # no transform divergence
        assert max(abs(v) for v in it["delta"].values()) < 1e-6
        # room association matches
        assert it["room_association"]["match"] is True
        # canonical is the source of truth (scene furniture == canonical, by uid)
        assert it["canonical_source_of_truth_match"] is True


# Bedroom 1 real furniture trace
def test_bedroom1_furniture_preserved():
    audit = build_audit(FID)
    b1 = [i for i in audit["items"] if i["room_name"] == "Bedroom 1"]
    types = {i["item_type"] for i in b1}
    assert "bed" in types and "wardrobe" in types and "dressing-table" in types
    for i in b1:
        assert max(abs(v) for v in i["delta"].values()) < 1e-6
        assert i["canonical_source_of_truth_match"] is True


# ── STEP 4 (backend half): the authoritative per-room scene each base PNG must render.
# The actual PNG-capture correspondence is verified in the browser (evidence artifact
# base_render_png_evidence.json); this asserts the scene content that defines it.
def test_base_render_expected_room_content():
    audit = build_audit(FID)
    by_room: dict[str, set[str]] = {}
    for i in audit["items"]:
        by_room.setdefault(i["room_name"], set()).add(i["item_type"])
    # Every bedroom's base scene MUST contain a bed (regression: bedroom != living).
    for bedroom in ("Bedroom 1", "Bedroom 2", "Bedroom 3"):
        assert "bed" in by_room.get(bedroom, set()), f"{bedroom} base scene must contain a bed"
        assert "lounger-sofa" not in by_room.get(bedroom, set()), f"{bedroom} must not contain sofas"
    # Living's base scene contains living furniture, not a bed.
    assert "lounger-sofa" in by_room.get("Living Area", set())
    assert "bed" not in by_room.get("Living Area", set())
