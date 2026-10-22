"""Tests for Phase 1-24: 6-room dynamic discovery, sequential concurrency, bounded retry backoff, and partial generation preservation."""

import pytest
import unittest.mock as mock
from app.services import prompt_service, generation_service
from app.services.ai.nvidia_flux_adapter import _clean_prompt
from app.services.ai.base import GenerationRequest, AIProviderError
from app.schemas.generation import GenerationResponse


def _sample_six_room_canonical():
    """Authoritative representation of the user's real 6-room 3BHK layout."""
    return {
        "furniture": [
            # Living Area (2 sofas in seating proximity + console + window + door)
            {"uid": "l_sofa1", "item_id": "lounger-sofa", "cx": 1872.0, "cy": 1032.0, "w": 220, "h": 90, "rotation": 0},
            {"uid": "l_sofa2", "item_id": "lounger-sofa", "cx": 1675.0, "cy": 1106.0, "w": 200, "h": 90, "rotation": 0},
            {"uid": "l_tv", "item_id": "console", "cx": 1676.0, "cy": 566.0, "w": 180, "h": 45, "rotation": 0},
            {"uid": "l_door", "item_id": "door", "cx": 1890.0, "cy": 568.0, "w": 90, "h": 90, "rotation": 0},
            {"uid": "l_win", "item_id": "window", "cx": 1813.0, "cy": 1204.0, "w": 150, "h": 20, "rotation": 0},
            # Kitchen (base units + chimney)
            {"uid": "k_base1", "item_id": "kitchen-base", "cx": 1604.0, "cy": 389.0, "w": 240, "h": 60, "rotation": 0},
            {"uid": "k_base2", "item_id": "kitchen-base", "cx": 1395.0, "cy": 243.0, "w": 240, "h": 60, "rotation": 0},
            {"uid": "k_chim", "item_id": "chimney", "cx": 1229.0, "cy": 368.0, "w": 90, "h": 50, "rotation": 0},
            # Dining Area (table + doors)
            {"uid": "d_tbl", "item_id": "dining-table", "cx": 1210.0, "cy": 632.0, "w": 150, "h": 90, "rotation": 0},
            {"uid": "d_d1", "item_id": "door", "cx": 1013.0, "cy": 948.0, "w": 90, "h": 90, "rotation": 0},
            {"uid": "d_d2", "item_id": "door", "cx": 1088.0, "cy": 729.0, "w": 90, "h": 90, "rotation": 0},
            {"uid": "d_d3", "item_id": "door", "cx": 1161.0, "cy": 942.0, "w": 90, "h": 90, "rotation": 0},
            {"uid": "d_d4", "item_id": "door", "cx": 1076.0, "cy": 421.0, "w": 90, "h": 90, "rotation": 0},
            # Bedroom 1 (bed + nightstands + wardrobe + dressing + door + window)
            {"uid": "b1_bed", "item_id": "bed", "cx": 504.0, "cy": 674.0, "w": 180, "h": 200, "rotation": 0},
            {"uid": "b1_st1", "item_id": "side-table", "cx": 402.0, "cy": 822.0, "w": 45, "h": 45, "rotation": 0},
            {"uid": "b1_st2", "item_id": "side-table", "cx": 402.0, "cy": 541.0, "w": 45, "h": 45, "rotation": 0},
            {"uid": "b1_wdr", "item_id": "wardrobe", "cx": 549.0, "cy": 830.0, "w": 180, "h": 60, "rotation": 0},
            {"uid": "b1_dr", "item_id": "dressing-table", "cx": 725.0, "cy": 836.0, "w": 100, "h": 50, "rotation": 0},
            {"uid": "b1_win", "item_id": "window", "cx": 333.0, "cy": 676.0, "w": 150, "h": 20, "rotation": 0},
            # Bedroom 2 (bed + nightstands + wardrobe + dressing + window)
            {"uid": "b2_bed", "item_id": "bed", "cx": 1305.0, "cy": 1257.0, "w": 160, "h": 200, "rotation": 0},
            {"uid": "b2_st1", "item_id": "side-table", "cx": 1437.0, "cy": 1314.0, "w": 45, "h": 45, "rotation": 0},
            {"uid": "b2_st2", "item_id": "side-table", "cx": 1166.0, "cy": 1315.0, "w": 45, "h": 45, "rotation": 0},
            {"uid": "b2_wdr", "item_id": "wardrobe", "cx": 1148.0, "cy": 1162.0, "w": 160, "h": 60, "rotation": 0},
            {"uid": "b2_dr", "item_id": "dressing-table", "cx": 1430.0, "cy": 953.0, "w": 100, "h": 50, "rotation": 0},
            {"uid": "b2_win", "item_id": "window", "cx": 1290.0, "cy": 1382.0, "w": 150, "h": 20, "rotation": 0},
            # Bedroom 3 (bed + nightstands + wardrobe + dressing + door + window)
            {"uid": "b3_bed", "item_id": "bed", "cx": 869.0, "cy": 1407.0, "w": 160, "h": 200, "rotation": 0},
            {"uid": "b3_st1", "item_id": "side-table", "cx": 1000.0, "cy": 1494.0, "w": 45, "h": 45, "rotation": 0},
            {"uid": "b3_st2", "item_id": "side-table", "cx": 734.0, "cy": 1493.0, "w": 45, "h": 45, "rotation": 0},
            {"uid": "b3_wdr", "item_id": "wardrobe", "cx": 1023.0, "cy": 1241.0, "w": 160, "h": 60, "rotation": 0},
            {"uid": "b3_dr", "item_id": "dressing-table", "cx": 721.0, "cy": 1110.0, "w": 100, "h": 50, "rotation": 0},
            {"uid": "b3_win", "item_id": "window", "cx": 875.0, "cy": 1546.0, "w": 150, "h": 20, "rotation": 0},
        ],
        "design_intent": {"style": "Modern Luxury", "mood": "Serene and refined"},
    }


def test_six_room_floor_plan_dynamic_discovery():
    """Verify that the real 6-room floor plan dynamically discovers exactly 6 rooms without hardcoding."""
    plan = _sample_six_room_canonical()
    eligible = prompt_service.get_eligible_sections(plan)
    assert len(eligible) == 6
    assert eligible == [
        "Living Area",
        "Kitchen",
        "Dining Area",
        "Bedroom 1",
        "Bedroom 2",
        "Bedroom 3",
    ]


def test_six_room_prompts_and_inventory_preservation():
    """Verify that 6 room prompts are created with inventory and geometry locked."""
    plan = _sample_six_room_canonical()
    _, rooms = prompt_service.build_room_prompts(plan, plan.get("design_intent"))
    assert len(rooms) == 6
    labels = [r[0] for r in rooms]
    assert labels == [
        "Living Area",
        "Kitchen",
        "Dining Area",
        "Bedroom 1",
        "Bedroom 2",
        "Bedroom 3",
    ]

    # Check that living prompt contains both sofa pieces
    living_prompt = next(r[1] for r in rooms if r[0] == "Living Area")
    assert "Loungers Sofa" in living_prompt
    # Inventory is front-loaded into the opening sentence.
    assert "that contains exactly:" in living_prompt

    # Check that bedroom 1 contains bed and 2 side tables
    b1_prompt = next(r[1] for r in rooms if r[0] == "Bedroom 1")
    assert "1x Bed" in b1_prompt
    assert "2x Side Table" in b1_prompt


def test_clean_prompt_modern_contemporary_suffix():
    """Verify that clean prompt adds Premium Modern Contemporary luxury suffix."""
    raw = "Camera at eye level looking across Bedroom 1. Exact furniture: 1 bed, 2 side tables."
    cleaned = _clean_prompt(raw)
    assert "Premium Modern Contemporary" in cleaned
    assert "warm 3000K concealed architectural cove lighting" in cleaned
    assert "35mm lens, natural perspective, straight vertical walls" in cleaned


def test_generation_service_six_rooms_end_to_end():
    """Verify generation service with 6-room floor plan preserves all 6 rooms and attaches room_geometry."""
    file_id = "f6b65d2b-4f96-4931-9f08-67dbd09776f6"
    from app.services.ai.mock_adapter import MockAdapter
    from app.services.ai import registry

    mock_adapter = MockAdapter()
    with mock.patch.object(registry, "get_adapter", return_value=mock_adapter):
        resp = generation_service.generate(
            file_id=file_id,
            provider="mock",
            count=1,
            design_intent={"style": "Modern Luxury"},
            all_sections=False,
            fresh_generation=True,
        )
        assert resp.status == "completed"
        assert resp.requested_rooms == [
            "Living Area",
            "Kitchen",
            "Dining Area",
            "Bedroom 1",
            "Bedroom 2",
            "Bedroom 3",
        ]
        assert resp.successful_rooms == resp.requested_rooms
        assert resp.failed_rooms is None
        assert len(resp.images) == 6
        for idx, img in enumerate(resp.images, start=1):
            assert img.design_index == idx
            assert img.total_designs == 6
            assert img.label == resp.requested_rooms[idx - 1]
            assert img.room_geometry is not None


def test_generation_service_partial_preservation_when_room_fails():
    """Verify that when a room generation fails, status is partial and total_designs remains 6."""
    file_id = "f6b65d2b-4f96-4931-9f08-67dbd09776f6"
    from app.services.ai.mock_adapter import MockAdapter
    from app.services.ai import registry

    class FlakyAdapter(MockAdapter):
        def generate(self, request):
            if request.room_label == "Dining Area":
                raise AIProviderError("mock", "Simulated error", 502)
            return super().generate(request)

    with mock.patch.object(registry, "get_adapter", return_value=FlakyAdapter()):
        resp = generation_service.generate(
            file_id=file_id,
            provider="mock",
            count=1,
            design_intent={"style": "Modern Luxury"},
            all_sections=False,
            fresh_generation=True,
        )
        assert resp.status == "partial"
        assert len(resp.requested_rooms) == 6
        assert "Dining Area" in resp.failed_rooms
        assert "Dining Area" not in resp.successful_rooms
        assert len(resp.images) == 5
        for img in resp.images:
            assert img.total_designs == 6
        # The real per-room provider error is surfaced (Phase 2), not swallowed.
        assert resp.room_errors and any(rerr.get("room") == "Dining Area" for rerr in resp.room_errors)


def test_generation_total_failure_returns_usable_failed_response():
    """When EVERY room fails, generate() must NOT raise a bare 502 — it returns a
    usable status='failed' response carrying the real provider error (Phase 2/4),
    and the record is listable as FAILED (Phase 3)."""
    file_id = "f6b65d2b-4f96-4931-9f08-67dbd09776f6"
    from app.services.ai import registry
    from app.services.ai.mock_adapter import MockAdapter

    class AllFail(MockAdapter):
        def generate(self, request):
            raise AIProviderError("mock", "HTTP 500: Internal Server Error", 502)

    with mock.patch.object(registry, "get_adapter", return_value=AllFail()):
        resp = generation_service.generate(
            file_id=file_id, provider="mock", count=1,
            design_intent={"style": "Modern Luxury"},
            requested_rooms=["Living Area", "Kitchen"], fresh_generation=True,
        )
    assert resp.status == "failed"
    assert resp.images == []
    assert resp.error and "500" in resp.error
    assert resp.room_errors and all(rerr.get("status") == 502 for rerr in resp.room_errors)
    # The failed generation is listable (endpoint must not 500 on it).
    listed = generation_service.list_generations(file_id, limit=3)
    assert any(g.id == resp.id and g.status == "failed" for g in listed)
