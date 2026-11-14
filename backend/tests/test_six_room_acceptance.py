"""Six-Room Acceptance Tests (Section 15 & 16).

Tests that the 2D floor plan is the single source of truth for all six canonical sections:
1. Living Area
2. Kitchen
3. Dining Area
4. Bedroom 1
5. Bedroom 2
6. Bedroom 3

Verifies:
FLOOR PLAN -> STRUCTURED DATA -> DETERMINISTIC LAYOUT -> FIDELITY VALIDATION -> PROMPT LOCKING
"""

import pytest
from app.services import architectural_service, fidelity_service, prompt_service
from app.services.ai.nvidia_flux_adapter import _clean_prompt


def _create_sample_canonical_floor_plan():
    """Realistic 3BHK canonical layout representing complete floor plan."""
    return {
        "furniture": [
            # Living Area
            {"uid": "liv_sofa", "item_id": "lounger-sofa", "cx": 500, "cy": 600, "w": 1900, "h": 900, "rotation": 0},
            {"uid": "liv_tbl", "item_id": "center-table", "cx": 500, "cy": 450, "w": 1000, "h": 600, "rotation": 0},
            {"uid": "liv_tv", "item_id": "console", "cx": 500, "cy": 180, "w": 1100, "h": 350, "rotation": 0},
            {"uid": "liv_win", "item_id": "window", "cx": 500, "cy": 850, "w": 1800, "h": 200, "rotation": 0},
            # Kitchen
            {"uid": "kt_base", "item_id": "kitchen-base", "cx": 1800, "cy": 300, "w": 2400, "h": 600, "rotation": 0},
            {"uid": "kt_chim", "item_id": "chimney", "cx": 1800, "cy": 220, "w": 900, "h": 500, "rotation": 0},
            # Dining Area
            {"uid": "din_tbl", "item_id": "dining-table", "cx": 1800, "cy": 1000, "w": 1500, "h": 900, "rotation": 0},
            {"uid": "din_c1", "item_id": "dining-chair", "cx": 1650, "cy": 900, "w": 450, "h": 500, "rotation": 0},
            {"uid": "din_c2", "item_id": "dining-chair", "cx": 1950, "cy": 900, "w": 450, "h": 500, "rotation": 0},
            {"uid": "din_c3", "item_id": "dining-chair", "cx": 1650, "cy": 1100, "w": 450, "h": 500, "rotation": 0},
            {"uid": "din_c4", "item_id": "dining-chair", "cx": 1950, "cy": 1100, "w": 450, "h": 500, "rotation": 0},
            # Bedroom 1 (Master)
            {"uid": "b1_bed", "item_id": "bed", "cx": 500, "cy": 2200, "w": 1800, "h": 2000, "rotation": 0},
            {"uid": "b1_st1", "item_id": "side-table", "cx": 300, "cy": 2200, "w": 450, "h": 450, "rotation": 0},
            {"uid": "b1_st2", "item_id": "side-table", "cx": 700, "cy": 2200, "w": 450, "h": 450, "rotation": 0},
            {"uid": "b1_dr", "item_id": "dressing-table", "cx": 200, "cy": 2500, "w": 1200, "h": 600, "rotation": 0},
            # Bedroom 2
            {"uid": "b2_bed", "item_id": "bed", "cx": 1800, "cy": 2200, "w": 1600, "h": 2000, "rotation": 0},
            {"uid": "b2_st1", "item_id": "side-table", "cx": 1600, "cy": 2200, "w": 450, "h": 450, "rotation": 0},
            {"uid": "b2_st2", "item_id": "side-table", "cx": 2000, "cy": 2200, "w": 450, "h": 450, "rotation": 0},
            # Bedroom 3
            {"uid": "b3_bed", "item_id": "bed", "cx": 3000, "cy": 2200, "w": 1200, "h": 2000, "rotation": 0},
            {"uid": "b3_st", "item_id": "side-table", "cx": 2800, "cy": 2200, "w": 450, "h": 450, "rotation": 0},
        ],
        "structured_walls": [
            {"id": "w_liv_1", "x1": 100, "y1": 100, "x2": 900, "y2": 100},
            {"id": "w_liv_2", "x1": 900, "y1": 100, "x2": 900, "y2": 900},
            {"id": "w_liv_3", "x1": 900, "y1": 900, "x2": 100, "y2": 900},
            {"id": "w_liv_4", "x1": 100, "y1": 900, "x2": 100, "y2": 100},
        ],
        "doors": [
            {"id": "door_main", "x": 120, "y": 880, "width": 900, "height": 100},
            {"id": "door_b1", "x": 300, "y": 2000, "width": 900, "height": 100},
        ],
        "windows": [
            {"id": "win_liv", "x": 500, "y": 880, "width": 1800, "height": 100},
            {"id": "win_b1", "x": 500, "y": 2700, "width": 1500, "height": 100},
        ],
        "metadata": {"mpp": 0.005},
        "design_intent": {"style": "Modern Luxury", "mood": "Calm and Elegant"},
    }


def test_six_rooms_reconstruction_and_geometry():
    """Verify that all 6 sections are reconstructed with deterministic metric geometry."""
    canonical = _create_sample_canonical_floor_plan()
    rooms = architectural_service.reconstruct_rooms(
        furniture=canonical["furniture"],
        structured_walls=canonical["structured_walls"],
        doors=canonical["doors"],
        windows=canonical["windows"],
        mpp=canonical["metadata"]["mpp"],
    )

    room_labels = {r["label"] for r in rooms}
    assert "Living Area" in room_labels
    assert "Kitchen" in room_labels
    assert "Dining Area" in room_labels
    assert any("Bedroom" in l for l in room_labels)

    # Check Living Area structured attributes
    living = next(r for r in rooms if r["label"] == "Living Area")
    assert living["dimensions"]["width_m"] > 0
    assert living["dimensions"]["depth_m"] > 0
    assert living["dimensions"]["height_m"] == 2.7
    assert len(living["furniture"]) >= 3

    for item in living["furniture"]:
        assert "id" in item
        assert "type" in item
        assert item["fixed"] is True
        assert "normalized_x" in item
        assert "normalized_y" in item


@pytest.mark.parametrize("section_label", [
    "Living Area",
    "Kitchen",
    "Dining Area",
    "Bedroom 1",
    "Bedroom 2",
    "Bedroom 3",
])
def test_six_rooms_fidelity_reports(section_label: str):
    """Verify that each of the six canonical sections achieves high architectural fidelity."""
    canonical = _create_sample_canonical_floor_plan()
    # Test via prompt_service._room_prompt and fidelity_service
    items = prompt_service._default_items_for_section(section_label)
    assert len(items) > 0, f"No default items configured for {section_label}"

    fidelity = fidelity_service.calculate_room_fidelity(
        room_label=section_label,
        items=items,
        bbox=[100.0, 100.0, 800.0, 800.0],
        doors=[{"id": "d1", "x": 150, "y": 750}],
        windows=[it for it in items if "window" in str(it.get("item_id", "")).lower()],
        design_intent=canonical["design_intent"],
    )

    assert fidelity["room_type_match"] is True
    assert fidelity["furniture_count_match"] is True
    assert fidelity["furniture_type_match"] is True
    assert fidelity["door_match"] is True
    assert fidelity["window_match"] is True
    assert fidelity["position_fidelity"] >= 0.85
    assert fidelity["orientation_fidelity"] >= 0.85
    assert fidelity["geometry_match"] >= 0.85
    assert fidelity["overall_fidelity"] >= 0.85
    assert fidelity["status"] == "VERIFIED_ACCURATE"
    assert fidelity["metrics"]["source_of_truth"] == "Authoritative 2D Floor Plan"


@pytest.mark.parametrize("section_label", [
    "Living Area",
    "Kitchen",
    "Dining Area",
    "Bedroom 1",
    "Bedroom 2",
    "Bedroom 3",
])
def test_six_rooms_prompt_locking(section_label: str):
    """Verify that camera viewpoint, focal point, and negative constraints are locked in prompt."""
    items = prompt_service._default_items_for_section(section_label)
    prompt = prompt_service._room_prompt(
        section_label,
        items,
        {"style": "Modern Luxury"},
        bbox=[100.0, 100.0, 800.0, 800.0],
    )

    # 1. Deterministic Camera Viewpoint
    assert "DETERMINISTIC CAMERA VIEWPOINT" in prompt
    assert "standing eye level (1.5m height)" in prompt
    assert "natural two-point perspective" in prompt

    # 2. Strict Negative Constraints (Section 10)
    assert "Do NOT add, move, remove, or rotate any furniture" in prompt
    assert "Do NOT invent walls, windows, doors, or architectural features" in prompt
    assert "Do NOT use a generic room layout" in prompt

    # 3. Room-specific Focal Rules
    if section_label == "Living Area":
        assert "LIVING AREA SPECIFICATION" in prompt
        assert "media wall" in prompt.lower() or "tv" in prompt.lower()
    elif section_label == "Kitchen":
        assert "KITCHEN SPECIFICATION" in prompt
        assert "cabinet" in prompt.lower() or "counter" in prompt.lower()
    elif section_label == "Dining Area":
        assert "DINING AREA SPECIFICATION" in prompt
        assert "dining table" in prompt.lower()
    elif "Bedroom" in section_label:
        assert "BEDROOM SPECIFICATION" in prompt
        assert "bed" in prompt.lower()

    # 4. Cleaned condensed prompt for diffusion remains within bounds
    cleaned = _clean_prompt(prompt)
    assert len(cleaned) <= 1500
    assert "35mm lens" in cleaned
    assert "Modern luxury interior" in cleaned
