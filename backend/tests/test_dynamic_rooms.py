"""Acceptance tests for Dynamic Room Discovery, Cache Bypass, and Controlled Style Variations (Phases 2, 3, 5, 6, 8, 10, 22, 23, 24, 25)."""

import pytest
from app.services import prompt_service


def _make_item(uid: str, item_id: str, cx: float, cy: float, w: float, h: float, rot: float = 0.0) -> dict:
    return {"uid": uid, "item_id": item_id, "cx": cx, "cy": cy, "w": w, "h": h, "rotation": rot}


def test_dynamic_five_room_discovery():
    """Verify that a 5-room floor plan (Living, Kitchen, Dining, Bedroom 1, Bedroom 2) derives exactly 5 sections."""
    plan = {
        "furniture": [
            # Living
            _make_item("l_sofa", "lounger-sofa", 500, 500, 1900, 900),
            # Kitchen
            _make_item("k_base", "kitchen-base", 1800, 300, 2400, 600),
            # Dining
            _make_item("d_table", "dining-table", 1800, 1000, 1500, 900),
            # Bedroom 1
            _make_item("b1_bed", "bed", 500, 2000, 1800, 2000),
            # Bedroom 2
            _make_item("b2_bed", "bed", 1800, 2000, 1600, 2000),
        ]
    }
    eligible = prompt_service.get_eligible_sections(plan)
    assert len(eligible) == 5
    assert eligible == ["Living Area", "Kitchen", "Dining Area", "Bedroom 1", "Bedroom 2"]

    _, prompts = prompt_service.build_room_prompts(plan, {"style": "Modern Luxury"})
    labels = [lbl for lbl, _p, _w, _h in prompts]
    assert len(labels) == 5
    assert labels == ["Living Area", "Kitchen", "Dining Area", "Bedroom 1", "Bedroom 2"]


def test_dynamic_seven_room_discovery_with_four_bedrooms():
    """Verify that a 7-room floor plan (Living, Kitchen, Dining, 4 Bedrooms) derives exactly 7 sections."""
    plan = {
        "furniture": [
            # Living
            _make_item("l_sofa", "lounger-sofa", 500, 500, 1900, 900),
            # Kitchen
            _make_item("k_base", "kitchen-base", 1800, 300, 2400, 600),
            # Dining
            _make_item("d_table", "dining-table", 1800, 1000, 1500, 900),
            # Bedroom 1 (top-left)
            _make_item("b1_bed", "bed", 500, 2000, 1800, 2000),
            # Bedroom 2 (top-right)
            _make_item("b2_bed", "bed", 1800, 2000, 1600, 2000),
            # Bedroom 3 (bottom-left)
            _make_item("b3_bed", "bed", 500, 3500, 1600, 2000),
            # Bedroom 4 (bottom-right)
            _make_item("b4_bed", "bed", 1800, 3500, 1600, 2000),
        ]
    }
    eligible = prompt_service.get_eligible_sections(plan)
    assert len(eligible) == 7
    assert eligible == [
        "Living Area",
        "Kitchen",
        "Dining Area",
        "Bedroom 1",
        "Bedroom 2",
        "Bedroom 3",
        "Bedroom 4",
    ]

    _, prompts = prompt_service.build_room_prompts(plan, {"style": "Modern Luxury"})
    labels = [lbl for lbl, _p, _w, _h in prompts]
    assert len(labels) == 7
    assert labels == [
        "Living Area",
        "Kitchen",
        "Dining Area",
        "Bedroom 1",
        "Bedroom 2",
        "Bedroom 3",
        "Bedroom 4",
    ]


def test_controlled_style_variation_across_seeds():
    """Verify that changing the seed produces controlled visual styling variation while geometry is locked."""
    plan = {
        "furniture": [
            _make_item("l_sofa", "lounger-sofa", 500, 500, 1900, 900),
            _make_item("l_tbl", "center-table", 500, 350, 1000, 600),
        ]
    }

    _, prompt_a = prompt_service.build_room_prompts(plan, {"style": "Modern Luxury"}, seed=100)
    _, prompt_b = prompt_service.build_room_prompts(plan, {"style": "Modern Luxury"}, seed=201)

    text_a = prompt_a[0][1]
    text_b = prompt_b[0][1]

    # Visual finishes differ between seed variations
    assert text_a != text_b

    # But authoritative inventory remains IDENTICAL
    assert "1x Loungers Sofa, 1x Center Table" in text_a
    assert "1x Loungers Sofa, 1x Center Table" in text_b
    assert "STRICT INVENTORY (DO NOT BREAK)" in text_a
    assert "STRICT INVENTORY (DO NOT BREAK)" in text_b


def test_camera_has_no_contradictions():
    """Verify that prompt does not contain contradictory 24mm vs 30mm/32mm camera lens directives."""
    plan = {
        "furniture": [
            _make_item("l_sofa", "lounger-sofa", 500, 500, 1900, 900),
        ]
    }
    _, prompts = prompt_service.build_room_prompts(plan, {"style": "Modern Luxury"})
    prompt = prompts[0][1]

    assert "24mm lens" not in prompt
    assert "30mm" in prompt or "32mm" in prompt
    assert "DETERMINISTIC CAMERA VIEWPOINT" in prompt
    assert "standing eye level (1.5m height)" in prompt
    assert "natural two-point perspective" in prompt
