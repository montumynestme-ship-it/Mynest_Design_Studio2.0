"""DB-free PDF-backed geometry-preservation tests for the SVG geometry reference.

Chain under test, with independently-established expected values at each hop:

  synthetic PDF (known coords, see synthetic_floorplan_provenance.md)
    → geometry_extraction_service.extract_walls   (independent extractor)
    → build a scene from the extracted geometry + a controlled canonical snapshot
    → svg_geometry_reference.build_geometry_reference  (UNIT UNDER TEST)

No database, no network, no fal. Expected wall/opening values come from extract_walls
(a different function than the builder) and from the fixture's documented coordinates;
the furniture footprint is checked against geometry_extraction_service._rotated_rect —
never against the SVG builder's own output.
"""

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from app.services import svg_geometry_reference as sgr
from app.services.geometry_extraction_service import _rotated_rect, extract_walls

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_floorplan.pdf"

# Independently-specified expected geometry (world px = PDF pt × 2) from the provenance doc.
EXPECTED_WALLS = [
    [200.0, 160.0, 1000.0, 160.0],
    [200.0, 640.0, 1000.0, 640.0],
    [200.0, 160.0, 200.0, 640.0],
    [1000.0, 160.0, 1000.0, 640.0],
]
EXPECTED_DOOR = {"cx": 400.0, "cy": 640.0}
EXPECTED_WINDOW = {"cx": 800.0, "cy": 160.0}
ROOM_BOUNDARY = [(200.0, 160.0), (1000.0, 160.0), (1000.0, 640.0), (200.0, 640.0)]

# Controlled canonical furniture snapshot (world px), inside the room.
BED = {"uid": "bed-1", "item_id": "bed", "cx": 600.0, "cy": 400.0, "w": 180.0, "h": 150.0, "rotation": 0.0}


@pytest.fixture(scope="module")
def extracted():
    assert FIXTURE.exists(), "run tests/fixtures/make_synthetic_floorplan.py to create the fixture"
    return extract_walls(str(FIXTURE))


def _scene(extracted, furniture):
    """Build a scene dict (as build_scene would shape it) from the EXTRACTED geometry +
    a controlled room boundary + the extracted openings split into the room."""
    doors = [o for o in extracted["openings"] if o["kind"] == "door"]
    windows = [o for o in extracted["openings"] if o["kind"] == "window"]
    return {
        "page": extracted["page"],
        "walls": extracted["walls"],
        "rooms": [
            {
                "id": "room-1",
                "label": "Test Room",
                "status": "CONFIRMED",
                "boundary": ROOM_BOUNDARY,
                "doors": doors,
                "windows": windows,
                "furniture": [{"id": f["uid"], "room_id": "room-1"} for f in furniture],
            }
        ],
    }


# ── Anchor 1: the extractor reproduces the fixture's known geometry ──────────────
def test_extractor_matches_fixture_known_geometry(extracted):
    assert extracted["page"]["width"] == 1200.0 and extracted["page"]["height"] == 800.0
    assert [[round(v, 1) for v in w] for w in extracted["walls"]] == EXPECTED_WALLS
    doors = [o for o in extracted["openings"] if o["kind"] == "door"]
    windows = [o for o in extracted["openings"] if o["kind"] == "window"]
    assert len(doors) == 1 and len(windows) == 1
    assert (doors[0]["cx"], doors[0]["cy"]) == (EXPECTED_DOOR["cx"], EXPECTED_DOOR["cy"])
    assert (windows[0]["cx"], windows[0]["cy"]) == (EXPECTED_WINDOW["cx"], EXPECTED_WINDOW["cy"])
    assert doors[0]["validation_status"] == "VALID"
    assert windows[0]["validation_status"] == "VALID"


# ── Anchor 2: the builder preserves walls + openings from the extracted scene ────
def test_svg_preserves_walls_and_openings(extracted):
    ref = sgr.build_geometry_reference({"furniture": [BED]}, _scene(extracted, [BED]))
    svg = ref.svg
    ET.fromstring(svg)  # well-formed
    # Every extracted wall segment appears verbatim (world px, 2-dp).
    for x0, y0, x1, y1 in EXPECTED_WALLS:
        assert f'x1="{x0:.2f}" y1="{y0:.2f}" x2="{x1:.2f}" y2="{y1:.2f}"' in svg
    # Door + window markers at the extracted centres.
    assert f'cx="{EXPECTED_DOOR["cx"]:.2f}" cy="{EXPECTED_DOOR["cy"]:.2f}"' in svg
    assert f'cx="{EXPECTED_WINDOW["cx"]:.2f}" cy="{EXPECTED_WINDOW["cy"]:.2f}"' in svg
    assert ref.meta["wall_count"] == 4 and ref.meta["opening_count"] == 2
    assert ref.meta["room_count"] == 1
    # Room boundary (world px) preserved as a polygon.
    assert 'points="200.00,160.00 1000.00,160.00 1000.00,640.00 200.00,640.00"' in svg


# ── Anchor 3: furniture inventory + transform vs _rotated_rect (not the builder) ──
def test_svg_preserves_furniture_inventory_and_transform(extracted):
    ref = sgr.build_geometry_reference({"furniture": [BED]}, _scene(extracted, [BED]))
    svg = ref.svg
    assert 'data-uid="bed-1"' in svg and 'data-item-id="bed"' in svg
    # Footprint equals the independent _rotated_rect for the controlled transform.
    corners = _rotated_rect(BED["cx"], BED["cy"], BED["w"], BED["h"], BED["rotation"])
    assert " ".join(f"{x:.2f},{y:.2f}" for x, y in corners) in svg
    # Room assignment taken from the proven scene (not guessed).
    item = next(i for i in ref.items if i["uid"] == "bed-1")
    assert item["room_id"] == "room-1" and item["room_assignment_source"] == "scene"
    assert ref.meta["furniture_drawn"] == 1


# ── Determinism ──────────────────────────────────────────────────────────────────
def test_svg_deterministic(extracted):
    a = sgr.build_geometry_reference({"furniture": [BED]}, _scene(extracted, [BED]), design_version_id="v1")
    b = sgr.build_geometry_reference({"furniture": [BED]}, _scene(extracted, [BED]), design_version_id="v1")
    assert a.svg == b.svg


# ── Honest handling of unknown / uncertain data (no silent correction) ───────────
def test_unknown_and_incomplete_furniture_reported_not_corrected(extracted):
    furniture = [
        {"uid": "u-known", "item_id": "bed", "cx": 600.0, "cy": 400.0, "w": 180.0, "h": 150.0, "rotation": 0.0},
        {"uid": "u-unknown", "item_id": "totally-unknown", "cx": 300.0, "cy": 300.0, "w": 40.0, "h": 40.0, "rotation": 0.0},
        {"uid": "u-incomplete", "item_id": "bed", "cx": 500.0, "cy": 500.0, "rotation": 0.0},  # missing w/h
    ]
    ref = sgr.build_geometry_reference({"furniture": furniture}, _scene(extracted, furniture))
    assert any("unknown item_id 'totally-unknown'" in w for w in ref.warnings)
    assert any("u-incomplete" in w and "missing required field" in w for w in ref.warnings)
    # Unknown type is still counted + drawn (just flagged); incomplete is NOT drawn
    # (never placed at a guessed size).
    assert ref.meta["furniture_count"] == 3
    assert ref.meta["furniture_drawn"] == 2
