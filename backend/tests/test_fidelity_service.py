"""Tests for the layout fidelity validation service (Section 11)."""

from app.services.fidelity_service import calculate_room_fidelity
from app.services import prompt_service


def test_calculate_room_fidelity_living_area():
    items = [
        {"item_id": "lounger-sofa", "cx": 500, "cy": 600, "w": 1900, "h": 900, "rotation": 0, "nearest_wall_id": "wall_001", "wall_relationship": "adjacent"},
        {"item_id": "center-table", "cx": 500, "cy": 450, "w": 1000, "h": 600, "rotation": 0, "nearest_wall_id": "wall_001", "wall_relationship": "freestanding"},
        {"item_id": "console", "cx": 500, "cy": 180, "w": 1100, "h": 350, "rotation": 0, "nearest_wall_id": "wall_002", "wall_relationship": "attached"},
        {"item_id": "window", "cx": 500, "cy": 850, "w": 1800, "h": 200, "rotation": 0, "nearest_wall_id": "wall_003", "wall_relationship": "attached"},
    ]
    bbox = [100.0, 100.0, 800.0, 800.0]
    doors = [{"id": "door_001", "x": 150, "y": 750, "width": 900, "height": 100}]
    windows = [{"id": "win_001", "x": 500, "y": 850, "width": 1800, "height": 100}]

    res = calculate_room_fidelity("Living Area", items, bbox, doors, windows)

    assert res["room_type_match"] is True
    assert res["furniture_count_match"] is True
    assert res["furniture_type_match"] is True
    assert res["position_fidelity"] >= 0.90
    assert res["orientation_fidelity"] >= 0.90
    assert res["door_match"] is True
    assert res["window_match"] is True
    assert res["geometry_match"] >= 0.90
    assert res["overall_fidelity"] >= 0.90
    assert res["status"] == "VERIFIED_ACCURATE"
    assert res["metrics"]["source_of_truth"] == "Authoritative 2D Floor Plan"


def test_deliberately_bad_room_scores_below_the_old_floor():
    """A genuinely wrong room must be able to score below 0.85 (no hidden floor)
    and must report real door/orientation/type mismatches, not hardcoded passes."""
    items = [
        # Two unrecognized items, far outside the room bounds, one rotated off-axis.
        {"item_id": "mystery-item-xyz", "cx": 9000, "cy": 9000, "w": 100, "h": 100, "rotation": 37},
        {"item_id": "another-unknown-thing", "cx": -9000, "cy": -9000, "w": 100, "h": 100,
         "rotation": 0},
        # A door-type item is present, but no structured door reaches this
        # room — a real geometry-propagation gap.
        {"item_id": "door", "cx": 500, "cy": 500, "w": 100, "h": 20, "rotation": 0},
    ]
    bbox = [0.0, 0.0, 1000.0, 1000.0]

    res = calculate_room_fidelity("Bedroom 1", items, bbox, doors=[], windows=[])

    assert res["furniture_type_match"] is False
    assert res["door_match"] is False
    assert res["position_fidelity"] < 1.0
    assert res["orientation_fidelity"] < 1.0
    assert res["overall_fidelity"] < 0.85
    assert res["status"] == "VALIDATED"


def test_deterministic_camera_spec_in_prompt():
    items = [
        {"item_id": "bed", "cx": 500, "cy": 300, "w": 1800, "h": 2000, "rotation": 0},
        {"item_id": "side-table", "cx": 300, "cy": 300, "w": 450, "h": 450, "rotation": 0},
        {"item_id": "side-table", "cx": 700, "cy": 300, "w": 450, "h": 450, "rotation": 0},
    ]
    bbox = [200.0, 100.0, 600.0, 800.0]
    doors = [{"id": "door_001", "x": 300, "y": 850}]

    prompt = prompt_service._room_prompt("Bedroom 1", items, {"style": "Modern Luxury"}, bbox=bbox, doors=doors)

    assert "DETERMINISTIC CAMERA VIEWPOINT" in prompt
    assert "standing eye level (1.5m height)" in prompt
    assert "natural two-point perspective" in prompt
    # No architectural reconstruction was supplied — this is a furniture-bbox
    # estimate and must say so honestly, not claim "EXACT".
    assert "APPROXIMATE ROOM DIMENSIONS & PROPORTIONS" in prompt
    assert "EXACT ROOM DIMENSIONS" not in prompt


def test_room_dimensions_say_exact_only_with_real_architectural_geometry():
    items = [{"item_id": "bed", "cx": 500, "cy": 300, "w": 1800, "h": 2000, "rotation": 0}]
    bbox = [200.0, 100.0, 600.0, 800.0]
    dims_meta = {"width_m": 4.5, "depth_m": 3.8, "height_m": 2.7, "area_sqm": 17.1}

    prompt = prompt_service._room_prompt(
        "Bedroom 1", items, {"style": "Modern Luxury"}, bbox=bbox,
        dims_meta=dims_meta, geom_source="architectural",
    )

    assert "EXACT ROOM DIMENSIONS & PROPORTIONS" in prompt
    assert "reconstructed architectural boundary" in prompt
    assert "4.5m width" in prompt
    assert "3.8m depth" in prompt
    assert "APPROXIMATE ROOM DIMENSIONS" not in prompt
    assert "BEDROOM SPECIFICATION" in prompt
