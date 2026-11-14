"""Regression tests for the canonical → SVG geometry reference.

All fixtures here are SYNTHETIC (clearly hand-built), chosen to exercise the data
contract: inventory/ID/type preservation, transform & room-assignment mapping,
architecture preservation, coordinate origin/scale, determinism, version binding,
stale rejection, missing-field reporting, and the optional SVG→PNG boundary.
"""

import re

import pytest

from app.services import svg_geometry_reference as sgr
from app.services.geometry_extraction_service import _rotated_rect


def _f(uid, item, cx, cy, w=100.0, h=100.0, rot=0.0):
    return {"uid": uid, "item_id": item, "cx": cx, "cy": cy, "w": w, "h": h, "rotation": rot}


def _canonical():
    return {
        "furniture": [
            _f("bed1", "bed", 200.0, 220.0, 180.0, 150.0, 90.0),
            _f("sofa1", "sofa", 650.0, 500.0, 220.0, 90.0, 0.0),
            {"uid": "tag1", "item_id": "room-tag", "cx": 0.0, "cy": 0.0, "w": 0.0, "h": 0.0, "rotation": 0.0},
        ]
    }


def _scene():
    return {
        "page": {"width": 1000.0, "height": 750.0, "scale": 2.0},
        "walls": [[0.0, 0.0, 1000.0, 0.0], [1000.0, 0.0, 1000.0, 750.0]],
        "rooms": [
            {
                "id": "bedroom-1",
                "label": "Bedroom 1",
                "status": "CONFIRMED",
                "boundary": [[10.0, 10.0], [400.0, 10.0], [400.0, 400.0], [10.0, 400.0]],
                "doors": [{"id": "door_001", "kind": "door", "cx": 50.0, "cy": 10.0}],
                "windows": [{"id": "window_001", "kind": "window", "cx": 200.0, "cy": 10.0}],
                "furniture": [{"id": "bed1", "room_id": "bedroom-1"}],
            },
            {
                "id": "living-area",
                "label": "Living Area",
                "status": "UNCERTAIN",
                "boundary": [[420.0, 10.0], [980.0, 10.0], [980.0, 700.0], [420.0, 700.0]],
                "doors": [],
                "windows": [],
                "furniture": [{"id": "sofa1", "room_id": "living-area"}],
            },
        ],
    }


def test_inventory_consistency_excludes_annotations():
    items, _ = sgr.reference_items(_canonical(), _scene())
    uids = {it["uid"] for it in items}
    assert uids == {"bed1", "sofa1"}  # room-tag annotation excluded, nothing invented


def test_id_and_type_preserved():
    items, _ = sgr.reference_items(_canonical(), _scene())
    bed = next(it for it in items if it["uid"] == "bed1")
    assert bed["item_id"] == "bed"
    assert bed["cx"] == 200.0 and bed["cy"] == 220.0 and bed["w"] == 180.0 and bed["h"] == 150.0
    assert bed["rotation"] == 90.0


def test_room_assignment_from_proven_scene():
    items, _ = sgr.reference_items(_canonical(), _scene())
    assert next(it for it in items if it["uid"] == "bed1")["room_id"] == "bedroom-1"
    assert next(it for it in items if it["uid"] == "sofa1")["room_id"] == "living-area"
    assert all(it["room_assignment_source"] == "scene" for it in items)


def test_room_assignment_falls_back_to_canonical_intent_not_guess():
    canonical = {"furniture": [_f("d1", "dining-table", 300.0, 300.0), ]}
    canonical["furniture"][0]["render_room"] = "KITCHEN"
    # No scene assignment for d1 → use the user-authored intent, labelled as such.
    items, _ = sgr.reference_items(canonical, {"rooms": []})
    assert items[0]["room_id"] == "KITCHEN"
    assert items[0]["room_assignment_source"] == "canonical_intent"


def test_footprint_matches_deterministic_renderer_math():
    ref = sgr.build_geometry_reference(_canonical(), _scene())
    # The bed polygon in the SVG must equal geometry_extraction_service._rotated_rect.
    expected = _rotated_rect(200.0, 220.0, 180.0, 150.0, 90.0)
    expected_pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in expected)
    assert expected_pts in ref.svg


def test_architecture_preserved_walls_rooms_openings():
    ref = sgr.build_geometry_reference(_canonical(), _scene())
    assert ref.meta["wall_count"] == 2
    assert ref.meta["opening_count"] == 2  # one door + one window
    assert ref.meta["room_count"] == 2
    assert "Bedroom 1" in ref.svg and "Living Area" in ref.svg
    # UNCERTAIN room is dashed; CONFIRMED is not (reviewer can tell them apart).
    assert "stroke-dasharray" in ref.svg
    # A wall segment is rendered verbatim in world px.
    assert 'x1="0.00" y1="0.00" x2="1000.00" y2="0.00"' in ref.svg


def test_coordinate_origin_and_scale():
    ref = sgr.build_geometry_reference(_canonical(), _scene())
    assert 'viewBox="0 0 1000.00 750.00"' in ref.svg
    assert ref.meta["coordinate_frame"] == "canonical_world_px"
    assert ref.meta["scale"] == 2.0


def test_deterministic_output():
    a = sgr.build_geometry_reference(_canonical(), _scene(), design_version_id="v1")
    b = sgr.build_geometry_reference(_canonical(), _scene(), design_version_id="v1")
    assert a.svg == b.svg


def test_version_binding_embedded():
    ref = sgr.build_geometry_reference(_canonical(), _scene(), design_version_id="dv-123")
    assert 'data-design-version-id="dv-123"' in ref.svg
    assert ref.meta["design_version_id"] == "dv-123"
    assert re.search(r'data-geometry-fingerprint="[0-9a-f]{16}"', ref.svg)


def test_stale_reference_rejected():
    ref = sgr.build_geometry_reference(_canonical(), _scene(), design_version_id="dv-1")
    ok, _ = sgr.validate_reference_freshness(
        ref.svg, expected_version_id="dv-1", expected_fingerprint=ref.meta["geometry_fingerprint"]
    )
    assert ok
    bad, reason = sgr.validate_reference_freshness(ref.svg, expected_version_id="dv-OTHER")
    assert not bad and "STALE_REFERENCE" in reason
    bad2, _ = sgr.validate_reference_freshness(ref.svg, expected_fingerprint="deadbeefdeadbeef")
    assert not bad2


def test_missing_transform_is_reported_not_drawn():
    canonical = {"furniture": [{"uid": "x1", "item_id": "bed", "cx": 100.0, "cy": 100.0, "rotation": 0.0}]}
    ref = sgr.build_geometry_reference(canonical, _scene())
    assert any("missing required field" in w for w in ref.warnings)
    assert ref.meta["furniture_drawn"] == 0  # never drawn at a guessed size


def test_unknown_item_id_reported_but_counted():
    canonical = {"furniture": [_f("u1", "totally-unknown", 300.0, 300.0, 40.0, 40.0, 0.0)]}
    ref = sgr.build_geometry_reference(canonical, _scene())
    assert any("unknown item_id" in w for w in ref.warnings)
    assert ref.meta["furniture_count"] == 1 and ref.meta["furniture_drawn"] == 1


def test_vectorless_plan_still_frames():
    # No scene page → view box derived from furniture bounds, valid SVG, no crash.
    ref = sgr.build_geometry_reference(_canonical(), {"rooms": []})
    assert ref.svg.startswith("<svg") and 'viewBox="0 0 ' in ref.svg
    assert ref.meta["wall_count"] == 0


def test_rasterize_boundary_is_optional():
    out = sgr.try_rasterize_png(sgr.build_geometry_reference(_canonical(), _scene()).svg)
    if out is None:
        pytest.skip("cairosvg not installed — rasterization behind the integration boundary")
    assert isinstance(out, bytes) and out[:8] == b"\x89PNG\r\n\x1a\n"
