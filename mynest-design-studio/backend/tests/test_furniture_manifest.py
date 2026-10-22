"""Authoritative furniture manifest (spec §2) + empty-room hard gate (spec §4)."""

from unittest import mock

import pytest

from app.services import furniture_manifest, generation_service


def _f(uid, item, cx, cy, w=100, h=100, rot=0):
    return {"uid": uid, "item_id": item, "cx": cx, "cy": cy, "w": w, "h": h, "rotation": rot}


def _bedroom_canonical():
    return {
        "furniture": [
            _f("b", "bed", 500, 350, 1800, 2000),
            _f("s1", "side-table", 300, 350, 450, 450),
            _f("s2", "side-table", 700, 350, 450, 450),
            _f("w", "window", 500, 800, 1500, 200),
        ]
    }


def test_manifest_counts_furniture_excludes_openings():
    m = furniture_manifest.room_manifest(_bedroom_canonical(), "Bedroom 1")
    assert m is not None
    assert m["furniture_count"] == 3  # bed + 2 side tables; window excluded
    assert m["counts"]["Side Table"] == 2
    assert m["counts"]["Bed"] == 1
    assert m["window_count"] == 1


def test_manifest_records_full_transform_per_item():
    m = furniture_manifest.room_manifest(_bedroom_canonical(), "Bedroom 1")
    bed = next(i for i in m["items"] if i["item_id"] == "bed")
    for key in ("uid", "item_id", "name", "cx", "cy", "w", "h", "rotation"):
        assert key in bed
    assert bed["cx"] == 500 and bed["w"] == 1800 and bed["rotation"] == 0


def test_manifest_empty_for_room_without_furniture():
    assert furniture_manifest.room_manifest({"furniture": []}, "Bedroom 1") is None


def test_gate_empty_room_never_calls_provider():
    """A room with no authoritative furniture must fail the gate before any provider call."""
    from app.services import floor_plan_service
    from app.services.ai.base import AIProviderAdapter, GenerationRequest

    class _WouldGenerate(AIProviderAdapter):
        name = "nvidia"
        model = "black-forest-labs/flux.1-dev"
        supports_control_image = True

        def __init__(self):
            self.called = False

        def generate(self, request: GenerationRequest):
            self.called = True
            return [b""]

    a = _WouldGenerate()
    with mock.patch("app.services.generation_service.AI_DEMO_MODE", False):
        with pytest.raises(floor_plan_service.FloorPlanError):
            generation_service._render_room(
                a, "nvidia", "Modern", ("Bedroom 1", "p", 1024, 768),
                ("proj", "fp", {"furniture": []}, None),
                generation_id="g", index=0, seed=1, fresh_generation=True,
                base_render=b"not-empty", scene_geometry_faithful=True,
            )
    assert a.called is False
