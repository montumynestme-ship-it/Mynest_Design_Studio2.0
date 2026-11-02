"""Draw Area (region render) — backend path tests. Offline only; NO paid provider call.

Proves the additive region path:
  * builds ONE section ("Selected Area") from the EXPLICIT selected uids, bypassing room
    grouping (label-independent);
  * validates fail-closed BEFORE any provider call (empty / unknown uid / bad bounds → 422);
  * reaches the (mock) provider as a single section and records region provenance;
  * leaves the room-based path unchanged when no region is supplied.

The deterministic-base-render CONTRACT (version/size) is the SAME shared code the room path
uses; it is covered by test_base_render_gate / test_handoff12 and applies to the region key by
construction (one loop over `rooms`). Here we assert region validation + wiring + no false
success, using the real generate() in AI_DEMO_MODE (MockAdapter placeholder, no network).
"""
from __future__ import annotations

import base64
from io import BytesIO
from unittest import mock

import pytest
from PIL import Image, ImageDraw

from app.services import (
    floor_plan_service,
    furniture_manifest,
    generation_service,
    prompt_service,
    scene_service,
)
from app.services.ai import registry
from app.services.ai.mock_adapter import MockAdapter

FID = "f6b65d2b-4f96-4931-9f08-67dbd09776f6"
REGION_LABEL = generation_service.REGION_SECTION_LABEL


def _png_dataurl(w=1216, h=832) -> str:
    """A NON-blank deterministic-base stand-in (passes the blank/corrupt base gate)."""
    img = Image.new("RGB", (w, h), (180, 160, 140))
    ImageDraw.Draw(img).rectangle([0, 0, w, h // 2], fill=(40, 60, 90))
    buf = BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

CANON = {
    "furniture": [
        {"uid": "a", "item_id": "lounger-sofa", "cx": 100, "cy": 100, "w": 50, "h": 30, "rotation": 0},
        {"uid": "b", "item_id": "dining-table", "cx": 300, "cy": 120, "w": 60, "h": 40, "rotation": 0},
        {"uid": "c", "item_id": "side-table", "cx": 900, "cy": 900, "w": 20, "h": 20, "rotation": 0},
    ]
}


class TrackingAdapter(MockAdapter):
    name = "tracking"
    model = "tracking-render"
    supports_control_image = True

    def __init__(self):
        self.rooms: list[str] = []

    def generate(self, request):
        self.rooms.append(request.room_label or "")
        return super().generate(request)


# ── _validate_region (pure; fail-closed) ──────────────────────────────────────
def test_validate_region_happy_path_preserves_order_and_bounds():
    items, bounds = generation_service._validate_region(
        {"selected_uids": ["b", "a"], "bounds": [0, 0, 400, 200]}, CANON
    )
    assert [i["uid"] for i in items] == ["b", "a"]  # selection order preserved
    assert bounds == [0.0, 0.0, 400.0, 200.0]


def test_validate_region_empty_selection_rejected():
    with pytest.raises(floor_plan_service.FloorPlanError) as e:
        generation_service._validate_region({"selected_uids": [], "bounds": [0, 0, 10, 10]}, CANON)
    assert "REGION_EMPTY" in e.value.detail


def test_validate_region_unknown_uid_rejected():
    with pytest.raises(floor_plan_service.FloorPlanError) as e:
        generation_service._validate_region(
            {"selected_uids": ["a", "nope"], "bounds": [0, 0, 10, 10]}, CANON
        )
    assert "REGION_UNKNOWN_UIDS" in e.value.detail


def test_validate_region_zero_area_bounds_rejected():
    with pytest.raises(floor_plan_service.FloorPlanError) as e:
        generation_service._validate_region({"selected_uids": ["a"], "bounds": [0, 0, 0, 200]}, CANON)
    assert "REGION_INVALID_BOUNDS" in e.value.detail


def test_validate_region_drops_room_tag_annotations():
    canon = {
        "furniture": [
            {"uid": "a", "item_id": "chair", "cx": 1, "cy": 1, "w": 1, "h": 1, "rotation": 0},
            {"uid": "t", "item_id": "room-tag", "cx": 2, "cy": 2, "w": 1, "h": 1, "rotation": 0},
        ]
    }
    items, _ = generation_service._validate_region(
        {"selected_uids": ["a", "t"], "bounds": [0, 0, 10, 10]}, canon
    )
    assert [i["uid"] for i in items] == ["a"]  # the room-tag annotation is dropped


def test_validate_region_only_annotations_is_empty():
    canon = {"furniture": [{"uid": "t", "item_id": "room-tag", "cx": 2, "cy": 2, "w": 1, "h": 1, "rotation": 0}]}
    with pytest.raises(floor_plan_service.FloorPlanError) as e:
        generation_service._validate_region({"selected_uids": ["t"], "bounds": [0, 0, 10, 10]}, canon)
    assert "REGION_EMPTY" in e.value.detail


def test_validate_region_dedupes_uids():
    items, _ = generation_service._validate_region(
        {"selected_uids": ["a", "a", "b"], "bounds": [0, 0, 10, 10]}, CANON
    )
    assert [i["uid"] for i in items] == ["a", "b"]


# ── build_region_prompt + manifest reflect ONLY the selected subset ───────────
def test_region_prompt_and_manifest_reflect_only_selected():
    items = [CANON["furniture"][0], CANON["furniture"][1]]  # a, b (not c)
    style, rooms = prompt_service.build_region_prompt(
        CANON, items, {"style": "Modern"}, [0, 0, 400, 200], seed=1, label=REGION_LABEL
    )
    assert len(rooms) == 1
    label, prompt_text, w, h = rooms[0]
    assert label == REGION_LABEL
    assert w > 0 and h > 0
    assert prompt_text  # non-empty prompt built from the subset

    manifest = furniture_manifest.build_room_manifest(items, room_label=REGION_LABEL)
    uids = sorted(e["uid"] for e in manifest["items"])
    assert uids == ["a", "b"]  # the un-selected 'c' is absent
    assert manifest["furniture_count"] == 2


def test_build_region_prompt_empty_items_returns_no_section():
    _, rooms = prompt_service.build_region_prompt(CANON, [], {}, [0, 0, 10, 10])
    assert rooms == []


# ── end-to-end region generate (AI_DEMO_MODE; MockAdapter; no network) ────────
def _real_uids(n: int) -> list[str]:
    _vid, _vn, canon = floor_plan_service.capture_generation_snapshot(FID)
    furn = canon.get("furniture", []) or []
    return [str(f["uid"]) for f in furn[:n]]


def test_region_renders_one_section_and_records_provenance(monkeypatch, tmp_path):
    uids = _real_uids(2)
    assert len(uids) == 2, "test design must have >=2 furniture items"
    adapter = TrackingAdapter()
    monkeypatch.setattr(generation_service, "DEBUG_ARTIFACTS_DIR", tmp_path)
    with mock.patch.object(registry, "get_adapter", return_value=adapter), mock.patch.object(
        generation_service, "AI_DEMO_MODE", True
    ):
        resp = generation_service.generate(
            file_id=FID,
            provider="tracking",
            count=1,
            design_intent={"style": "Modern"},
            region={
                "bounds": [0, 0, 1000, 1000],
                "selected_uids": uids,
                "include_partial": True,
                "label": REGION_LABEL,
            },
        )
    # Exactly ONE section, labeled "Selected Area" — grouping was bypassed.
    assert adapter.rooms == [REGION_LABEL], adapter.rooms
    assert [img.label for img in resp.images] == [REGION_LABEL]
    assert (resp.requested_rooms or []) == [REGION_LABEL]
    # Region provenance was recorded with the exact selected uids + bounds.
    prov = tmp_path / resp.id / "region_provenance.json"
    assert prov.is_file()
    import json

    data = json.loads(prov.read_text(encoding="utf-8"))
    assert data["selected_uids"] == uids
    assert data["bounds"] == [0, 0, 1000, 1000]
    assert data["label"] == REGION_LABEL


def test_region_empty_selection_never_calls_provider(monkeypatch):
    adapter = TrackingAdapter()
    with mock.patch.object(registry, "get_adapter", return_value=adapter), mock.patch.object(
        generation_service, "AI_DEMO_MODE", True
    ):
        with pytest.raises(floor_plan_service.FloorPlanError) as e:
            generation_service.generate(
                file_id=FID,
                provider="tracking",
                count=1,
                design_intent={"style": "Modern"},
                region={"bounds": [0, 0, 100, 100], "selected_uids": [], "include_partial": True},
            )
    assert "REGION_EMPTY" in e.value.detail
    assert adapter.rooms == []  # provider never invoked


def test_region_unknown_uid_never_calls_provider(monkeypatch):
    adapter = TrackingAdapter()
    with mock.patch.object(registry, "get_adapter", return_value=adapter), mock.patch.object(
        generation_service, "AI_DEMO_MODE", True
    ):
        with pytest.raises(floor_plan_service.FloorPlanError) as e:
            generation_service.generate(
                file_id=FID,
                provider="tracking",
                count=1,
                design_intent={"style": "Modern"},
                region={
                    "bounds": [0, 0, 100, 100],
                    "selected_uids": ["definitely-not-a-real-uid"],
                    "include_partial": True,
                },
            )
    assert "REGION_UNKNOWN_UIDS" in e.value.detail
    assert adapter.rooms == []


# ── §L region faithfulness (BASE_GEOMETRY_INVALID fix) ────────────────────────
def _scene_rooms():
    _vid, _vn, canon = floor_plan_service.capture_generation_snapshot(FID)
    scene = scene_service.build_scene(FID, canonical=canon)
    return scene.get("rooms", []) or []


def test_region_faithful_true_when_selected_items_in_confirmed_labels():
    rooms = _scene_rooms()
    rfm = generation_service._room_faithful_map(rooms)
    # Kitchen base (host label "Kitchen" is faithful via the CONFIRMED combined room) +
    # chimney/dining (host "Kitchen & Dining Area" CONFIRMED) → the region IS §L-faithful,
    # exactly like a per-room Kitchen render — NOT dragged down by unselected fallback rooms.
    sel = [
        "kitchen-base-1787478607029",
        "kitchen-base-1787478608231",
        "chimney-1787478686293",
        "dining-table-1787478800756",
    ]
    assert generation_service._region_scene_faithful(sel, rooms, rfm) is True


def test_region_faithful_false_for_unknown_or_unproven_or_empty():
    rooms = _scene_rooms()
    rfm = generation_service._room_faithful_map(rooms)
    # An item not placed in any reconstructed scene room cannot be verified → not faithful.
    assert generation_service._region_scene_faithful(["no-such-uid"], rooms, rfm) is False
    # Empty selection → not faithful.
    assert generation_service._region_scene_faithful([], rooms, rfm) is False
    # §L is NOT weakened: a room whose label has no CONFIRMED support still fails.
    synth = [{"label": "Store", "validation_status": "UNCERTAIN", "furniture": [{"uid": "x1"}]}]
    assert (
        generation_service._region_scene_faithful(
            ["x1"], synth, generation_service._room_faithful_map(synth)
        )
        is False
    )


def test_unfaithful_region_still_classified_base_geometry_invalid():
    # The gate still refuses an unfaithful region (no §L bypass): scene_geometry_faithful=False
    # with real furniture → BASE_GEOMETRY_INVALID (never a false pass).
    manifest = {"furniture_count": 2, "items": [{"uid": "a"}, {"uid": "b"}]}
    code, _ = generation_service._classify_base_gate(manifest, False, b"not-really-png")
    assert code == "BASE_GEOMETRY_INVALID"


def test_region_passes_sL_and_reaches_provider_in_gated_path(monkeypatch, tmp_path):
    # END-TO-END (real gated path, AI_DEMO_MODE=False, mocked adapter → NO paid call): the
    # selected Kitchen+Dining region now PASSES §L and dispatches, where before the fix it was
    # refused BASE_GEOMETRY_INVALID by inheriting the global (unselected-room) faithfulness.
    vid, _vn, canon = floor_plan_service.capture_generation_snapshot(FID)
    sel = [
        "kitchen-base-1787478607029",
        "kitchen-base-1787478608231",
        "chimney-1787478686293",
        "dining-table-1787478800756",
    ]
    present = {str(f.get("uid")) for f in canon.get("furniture", []) or []}
    assert set(sel) <= present, "test fixture uids must exist in the current snapshot"

    base_renders = {REGION_LABEL: _png_dataurl()}
    base_render_meta = {
        REGION_LABEL: {"design_version_id": vid, "room_key": REGION_LABEL, "width": 1216, "height": 832}
    }
    adapter = TrackingAdapter()
    monkeypatch.setattr(generation_service, "DEBUG_ARTIFACTS_DIR", tmp_path)
    with mock.patch.object(registry, "get_adapter", return_value=adapter), mock.patch.object(
        generation_service, "AI_DEMO_MODE", False
    ):
        resp = generation_service.generate(
            file_id=FID,
            provider="tracking",
            count=1,
            design_intent={"style": "Modern"},
            base_renders=base_renders,
            base_render_meta=base_render_meta,
            region={
                "bounds": [0, 0, 1000, 1000],
                "selected_uids": sel,
                "include_partial": True,
                "label": REGION_LABEL,
            },
        )
    assert REGION_LABEL not in (resp.failed_rooms or []), resp.room_errors
    assert adapter.rooms == [REGION_LABEL], adapter.rooms  # reached the (mock) provider
    assert [img.label for img in resp.images] == [REGION_LABEL]


# ── Arm B (Canny Control-LoRA) region request body — OFFLINE prep, no network/flag change ──
def test_arm_b_region_control_body_uses_base_as_control_and_init():
    """Proves the Canny request body for a region: the deterministic base fills BOTH the
    Canny structure control AND the colour init (Arm B), at the exact base dims. Exercises the
    REAL _build_control_body with region params — no HTTP, no provider call, no default change."""
    from app.services.ai import fal_flux_adapter as FA
    from app.services.ai.base import GenerationRequest

    base_uri = _png_dataurl()
    adapter = FA.FalFluxAdapter()
    req = GenerationRequest(
        prompt="[Selected Area]\nrender 2x Kitchen Base, 1x Chimney, 1x Dining Table",
        style=None,
        count=1,
        width=1216,
        height=832,
        seed=42,
        room_label=REGION_LABEL,
        control_image=b"x",
        structural_image=None,
    )
    body = adapter._build_control_body(req, base_uri, 1216, 832, None)
    assert body["control_lora_image_url"] == base_uri  # base = Canny structure control
    assert body["image_url"] == base_uri  # base ALSO = colour init (Arm B, FAL_CONTROL_USE_INIT)
    assert body["image_size"] == {"width": 1216, "height": 832}
    assert body["control_lora_strength"] == 1.0  # default (FAL_CONTROL_STRENGTH unset)
    assert body["num_images"] == 1 and body["output_format"] == "png"
    assert adapter.last_control_source == "base"  # NOT structural (no structural image)


def test_room_path_unchanged_when_no_region(monkeypatch):
    # Regression: without a region, the room-discovery path still produces real sections and
    # NEVER a "Selected Area" section (the region branch is fully inert when region is None).
    adapter = TrackingAdapter()
    with mock.patch.object(registry, "get_adapter", return_value=adapter), mock.patch.object(
        generation_service, "AI_DEMO_MODE", True
    ):
        resp = generation_service.generate(
            file_id=FID,
            provider="tracking",
            count=1,
            design_intent={"style": "Modern"},
            all_sections=False,
        )
    assert adapter.rooms, "room path should render at least one section"
    assert REGION_LABEL not in adapter.rooms
    assert all(img.label != REGION_LABEL for img in resp.images)
