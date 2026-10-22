"""Tests for the opening-geometry + 2D->3D placement AUDIT (STEP 1 and STEP 3).

Single owner for BOTH opening audits (no step-specific duplicate test files):
  * STEP 1 — wall-relative projection math (delegates to production `_project_on_wall`),
  * STEP 3 — the door/window 2D->3D placement validation (same-room, same-wall,
    same wall-relative position, width/height/rotation preserved, UNABLE_TO_VERIFY
    handling, Bedroom 1 window regression, shared-wall openings).
No production behavior is changed; assertions reuse the production pipeline + the
transcribed RoomScene3D transform via `scripts.opening_geometry_audit`.
"""

import math

import pytest

from app.services import scene_service
from scripts.opening_geometry_audit import _project_segment, build_audit, wall_relative

FID = "f6b65d2b-4f96-4931-9f08-67dbd09776f6"


def _wall(x1, y1, x2, y2):
    return {"id": "w", "x1": x1, "y1": y1, "x2": x2, "y2": y2}


# 1. horizontal wall projection
def test_horizontal_wall_projection():
    wr = wall_relative(_wall(0, 0, 100, 0), 25, 10)
    assert wr["normalized_position"] == pytest.approx(0.25)
    assert wr["distance_from_start"] == pytest.approx(25.0)
    assert wr["distance_from_end"] == pytest.approx(75.0)
    assert wr["wall_length"] == pytest.approx(100.0)
    assert wr["perpendicular_distance"] == pytest.approx(10.0)
    assert wr["direction_deg"] == pytest.approx(0.0)


# 2. vertical wall projection
def test_vertical_wall_projection():
    wr = wall_relative(_wall(0, 0, 0, 200), 5, 50)
    assert wr["normalized_position"] == pytest.approx(0.25)
    assert wr["distance_from_start"] == pytest.approx(50.0)
    assert wr["perpendicular_distance"] == pytest.approx(5.0)
    assert abs(wr["direction_deg"]) == pytest.approx(90.0)


# 3. opening centered on wall
def test_centered_on_wall():
    wr = wall_relative(_wall(0, 0, 80, 0), 40, 0)
    assert wr["normalized_position"] == pytest.approx(0.5)
    assert wr["distance_from_start"] == pytest.approx(wr["distance_from_end"])


# 4. opening near wall start
def test_near_wall_start():
    wr = wall_relative(_wall(0, 0, 100, 0), 3, 0)
    assert wr["normalized_position"] == pytest.approx(0.03)
    assert wr["distance_from_start"] < wr["distance_from_end"]


# 5. opening near wall end
def test_near_wall_end():
    wr = wall_relative(_wall(0, 0, 100, 0), 97, 0)
    assert wr["normalized_position"] == pytest.approx(0.97)
    assert wr["distance_from_end"] < wr["distance_from_start"]


# 6. multiple openings on the same wall keep distinct normalized positions
def test_multiple_openings_same_wall():
    wall = _wall(0, 0, 100, 0)
    a = wall_relative(wall, 20, 0)["normalized_position"]
    b = wall_relative(wall, 60, 0)["normalized_position"]
    c = wall_relative(wall, 90, 0)["normalized_position"]
    assert a == pytest.approx(0.2) and b == pytest.approx(0.6) and c == pytest.approx(0.9)
    assert len({a, b, c}) == 3


# 7. rotated / non-axis-aligned wall (45 deg)
def test_rotated_wall_projection():
    wall = _wall(0, 0, 100, 100)  # 45-degree wall, length ~141.42
    wr = wall_relative(wall, 50, 50)  # midpoint
    assert wr["normalized_position"] == pytest.approx(0.5)
    assert wr["wall_length"] == pytest.approx(math.hypot(100, 100), abs=1e-2)
    assert wr["direction_deg"] == pytest.approx(45.0)
    # A point off the 45-deg line projects to the nearest foot; perp > 0.
    off = wall_relative(wall, 60, 40)
    assert off["perpendicular_distance"] > 0


# audit delegates to the exact production projection
def test_audit_uses_production_projection():
    wall = _wall(10, 20, 110, 20)
    px, py, ang, perp, t = scene_service._project_on_wall(30, 25, wall)
    wr = wall_relative(wall, 30, 25)
    assert wr["normalized_position"] == pytest.approx(round(t, 4))
    assert wr["perpendicular_distance"] == pytest.approx(round(perp, 3))


# smoke: the real FID audit traces every opening incl. Bedroom 1, numerically
def test_fid_audit_traces_openings_including_bedroom1():
    audit = build_audit(FID)
    assert audit["design_version_id"] and audit["opening_count"] >= 1
    # Every opening has a source + either a numeric wall_relative or a documented reason.
    for o in audit["openings"]:
        assert set(o["source"]) >= {"cx", "cy", "width", "height", "rotation"}
        wr = o["wall_relative"]
        assert ("normalized_position" in wr) or (wr.get("value") is None and "reason" in wr)
    # Bedroom 1 window is present and traced.
    b1 = [o for o in audit["openings"] if o["room_name"] == "Bedroom 1" and o["type"] == "window"]
    assert b1, "Bedroom 1 window must be traced"
    w = b1[0]
    assert "cx" in w["source"] and "scene" in w


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3 — door/window 2D -> 3D placement (migrated into this single owner)
# ═══════════════════════════════════════════════════════════════════════════════

# affine (the 2D->3D transform) preserves normalized wall position
def test_affine_preserves_normalized_position():
    t2d, _perp, _len = _project_segment(0, 0, 100, 0, 30, 0)
    mpp, rcx, rcy = 0.01, 500, 500
    t3d, _p3, _l3 = _project_segment(
        (0 - rcx) * mpp, (0 - rcy) * mpp, (100 - rcx) * mpp, (0 - rcy) * mpp,
        (30 - rcx) * mpp, (0 - rcy) * mpp)
    assert t2d == pytest.approx(t3d)


def test_every_verified_opening_preserves_wall_relative_and_assoc():
    a = build_audit(FID)
    assert a["opening_count"] >= 1
    assert a["max_wall_relative_delta"] < 1e-6  # along-wall position preserved into 3D
    for o in a["openings"]:
        if o["status"] != "VERIFIED":
            continue
        assert o["room_association_match"] is True
        assert o["wall_association_match"] is True
        d = o["deltas"]
        assert d["wall_relative_normalized"] < 1e-6   # same wall-relative position
        assert abs(d["width_m"]) < 1e-6               # width preserved (x mpp)
        assert abs(d["height_m"]) < 1e-6              # height preserved (x mpp)
        assert abs(d["rotation_deg"]) < 1e-6          # rotation preserved (negated)
        assert o["first_divergence_stage"] == "NONE"


def test_unverifiable_openings_reported_not_passed():
    a = build_audit(FID)
    unver = [o for o in a["openings"] if o["status"] == "UNABLE_TO_VERIFY"]
    # The known source-insufficient openings must remain honest UNABLE_TO_VERIFY.
    for o in unver:
        assert o["wall"]["value"] is None and o["wall"].get("reason")
        assert "no supporting wall" in o["first_divergence_stage"]
    names = {(o["room_name"], o["type"]) for o in unver}
    assert ("Bedroom 3", "window") in names
    # The kitchen/dining open-plan door remains honestly UNABLE_TO_VERIFY (no supporting
    # wall). Its owning room is the shared open-plan polygon, labelled "Kitchen & Dining
    # Area" — match by substring so the valid co-label does not false-fail this check.
    assert any(t == "door" and "Kitchen" in rn for rn, t in names)


def test_bedroom1_window_verified_and_wall_relative_preserved():
    a = build_audit(FID)
    b1 = [o for o in a["openings"] if o["room_name"] == "Bedroom 1" and o["type"] == "window"]
    assert b1, "Bedroom 1 window must be present"
    o = b1[0]
    assert o["status"] == "VERIFIED" and o["wall"]["wall_id"] == "wall_086"
    assert o["deltas"]["wall_relative_normalized"] < 1e-6  # exact (unrounded) along-wall match
    # display values are rounded to different precisions (4dp vs 6dp); compare loosely
    assert o["wall_relative"]["normalized_position"] == pytest.approx(
        o["final_3d_wall_relative"]["normalized"], abs=1e-3)
    assert o["deltas"]["perp_removed_px"] > 0   # intentional on-wall projection
    assert o["width_exceeds_wall"] is True       # source-data note: window wider than wall fragment


def test_coverage_includes_doors_and_windows_editor_and_pdf():
    a = build_audit(FID)
    types = {o["type"] for o in a["openings"]}
    reprs = {o["representation"] for o in a["openings"]}
    assert "door" in types and "window" in types
    assert "editor" in reprs or "pdf" in reprs


def test_shared_wall_openings_keep_distinct_positions():
    a = build_audit(FID)
    by_wall: dict[str, list[float]] = {}
    for o in a["openings"]:
        if o["status"] == "VERIFIED":
            by_wall.setdefault(o["wall"]["wall_id"], []).append(o["final_3d_wall_relative"]["normalized"])
    for w, ns in by_wall.items():
        if len(ns) > 1:
            assert len({round(n, 4) for n in ns}) == len(ns), f"openings collide on {w}"


def test_step3_counts_regression():
    # Preserve the proven STEP 3 result: 11 verified, 2 UNABLE_TO_VERIFY, delta 0.
    a = build_audit(FID)
    assert a["verified_count"] == 11
    assert a["unable_to_verify_count"] == 2
    assert a["max_wall_relative_delta"] == 0
