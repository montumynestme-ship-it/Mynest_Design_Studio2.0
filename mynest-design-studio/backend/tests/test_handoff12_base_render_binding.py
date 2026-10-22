"""Handoff #12 — end-to-end base-render version binding.

The frontend now sends `base_render_meta` (design_version_id + room_key + width +
height) alongside `base_renders`, sourced from the `design_version_id` the /scene
response exposes. These tests prove the backend enforces that contract through the
real generate() path: a stale/wrong-room/wrong-size/missing-metadata capture is
rejected with a structured BASE_RENDER_* error and NEVER reaches FalFluxAdapter,
while correct metadata is not rejected by the contract.

Offline: the fal adapter's httpx.Client is patched to fail on any real network call,
so an invalid capture reaching fal would fail the test loudly.
"""

import base64
from io import BytesIO
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.main import app
from app.services import base_render_service, floor_plan_service, generation_service
from app.services.ai import fal_flux_adapter, registry
from app.services.ai.fal_flux_adapter import FalFluxAdapter

client = TestClient(app)
FID = "f6b65d2b-4f96-4931-9f08-67dbd09776f6"
ROOM = "Living Area"

PNG_1PX = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
    b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _png_dataurl(w=1216, h=832) -> str:
    img = Image.new("RGB", (w, h), (180, 160, 140))
    ImageDraw.Draw(img).rectangle([0, 0, w, h // 2], fill=(40, 60, 90))
    buf = BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _current_version(file_id: str) -> str:
    info = floor_plan_service.get_latest_version_info(file_id)
    assert info is not None
    return info[0]


def _png_bytes(w: int, h: int) -> bytes:
    img = Image.new("RGB", (w, h), (180, 160, 140))
    ImageDraw.Draw(img).rectangle([0, 0, w, h // 2], fill=(40, 60, 90))
    buf = BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


# ── DPR regression: the capture-path contract accepts a DPR=1 (1216×832) capture ─
# and keeps rejecting the old HiDPI DPR=2 (2432×1664) capture against 1216×832 meta.
def test_dpr1_capture_1216x832_accepted_by_contract():
    # After the fix, BaseRenderBatch renders at dpr=1 so the PNG is exactly 1216×832.
    v = base_render_service.validate_base_render(
        _png_bytes(1216, 832),
        expected_version_id="v1", declared_version_id="v1",
        expected_room_key="living-area", declared_room_key="living-area",
        expected_width=1216, expected_height=832,
    )
    assert v["ok"] is True and v["code"] is None
    assert (v["width"], v["height"]) == (1216, 832)


def test_hidpi_dpr2_capture_2432x1664_still_rejected():
    # The pre-fix HiDPI capture (CSS 1216×832 × dpr 2) must STILL be rejected against
    # 1216×832 metadata — the validation is NOT weakened.
    v = base_render_service.validate_base_render(
        _png_bytes(2432, 1664),
        expected_version_id="v1", declared_version_id="v1",
        expected_room_key="living-area", declared_room_key="living-area",
        expected_width=1216, expected_height=832,
    )
    assert v["ok"] is False and v["code"] == base_render_service.WRONG_SIZE
    assert (v["width"], v["height"]) == (2432, 1664)


def _run_generate(base_renders, base_render_meta):
    """Generate on FID with a REAL FalFluxAdapter but fal network boom-patched, so a
    capture that passes the contract AND reaches fal fails the test, while a rejected
    capture never touches the network. Returns (response, boom_mock)."""
    boom = mock.MagicMock(side_effect=AssertionError("fal network call attempted"))
    adapter = FalFluxAdapter()
    adapter.api_key = "test-key"
    adapter.arbitrary_image_effective = True
    with mock.patch.object(registry, "get_adapter", return_value=adapter), \
         mock.patch.object(generation_service, "AI_DEMO_MODE", False), \
         mock.patch.object(fal_flux_adapter.httpx, "Client", boom):
        resp = generation_service.generate(
            file_id=FID, provider="fal", count=1,
            design_intent={"style": "Modern"}, requested_rooms=[ROOM],
            fresh_generation=True,
            base_renders=base_renders,
            base_render_meta=base_render_meta,
        )
    return resp, boom


def _room_error_details(resp) -> str:
    return " ".join((e.get("detail") or "") for e in (resp.room_errors or []))


# ── /scene exposes the current design version id (version source) ────────────────
def test_scene_exposes_current_design_version_id():
    project = client.post("/api/projects", json={"name": "__h12__", "floor_count": 1}).json()
    pid, fid = project["id"], project["floors"][0]["id"]
    try:
        up = client.post(
            "/api/floor-plans/upload",
            files={"file": ("empty.png", BytesIO(PNG_1PX), "image/png")},
            data={"project_id": pid, "floor_id": fid},
        )
        plan_id = up.json()["id"]
        client.put(f"/api/floor-plans/{plan_id}/layout", json={"items": [
            {"uid": "u-1", "item_id": "bed", "cx": 500, "cy": 350, "w": 1800, "h": 2000, "rotation": 0},
        ]})
        scene = client.get(f"/api/floor-plans/{plan_id}/scene").json()
        assert "design_version_id" in scene
        assert scene["design_version_id"] == _current_version(plan_id)
    finally:
        client.delete(f"/api/projects/{pid}")


# ── stale version → REJECT, never reaches fal ───────────────────────────────────
def test_stale_version_rejected_before_fal():
    meta = {ROOM: {"design_version_id": "stale-version-xyz", "room_key": ROOM,
                   "width": 1216, "height": 832}}
    resp, boom = _run_generate({ROOM: _png_dataurl()}, meta)
    assert "BASE_RENDER_WRONG_VERSION" in _room_error_details(resp)
    boom.assert_not_called()


# ── wrong room → REJECT ─────────────────────────────────────────────────────────
def test_wrong_room_rejected_before_fal():
    meta = {ROOM: {"design_version_id": _current_version(FID), "room_key": "Kitchen",
                   "width": 1216, "height": 832}}
    resp, boom = _run_generate({ROOM: _png_dataurl()}, meta)
    assert "BASE_RENDER_WRONG_ROOM" in _room_error_details(resp)
    boom.assert_not_called()


# ── wrong dimensions → REJECT ───────────────────────────────────────────────────
def test_wrong_size_rejected_before_fal():
    # Declared 1216x832 but the PNG is 64x64 (e.g. a UI screenshot / wrong canvas).
    meta = {ROOM: {"design_version_id": _current_version(FID), "room_key": ROOM,
                   "width": 1216, "height": 832}}
    resp, boom = _run_generate({ROOM: _png_dataurl(64, 64)}, meta)
    assert "BASE_RENDER_WRONG_SIZE" in _room_error_details(resp)
    boom.assert_not_called()


# ── missing metadata for a room → REJECT (contract requires it) ──────────────────
def test_missing_metadata_rejected_before_fal():
    # base_render_meta is present (contract active) but has NO entry for this room.
    meta = {"some-other-room": {"design_version_id": _current_version(FID),
                                "room_key": "some-other-room", "width": 1216, "height": 832}}
    resp, boom = _run_generate({ROOM: _png_dataurl()}, meta)
    assert "BASE_RENDER_WRONG_VERSION" in _room_error_details(resp)  # cannot prove version
    boom.assert_not_called()


# ── correct metadata → NOT rejected by the contract ─────────────────────────────
def test_correct_metadata_passes_the_contract():
    meta = {ROOM: {"design_version_id": _current_version(FID), "room_key": ROOM,
                   "width": 1216, "height": 832}}
    resp, _boom = _run_generate({ROOM: _png_dataurl()}, meta)
    # The base-render contract must NOT reject correct metadata. (The room may still
    # fail downstream for a geometry reason or hit the fal boom — both prove the
    # contract itself passed; only a BASE_RENDER_* code would mean a false rejection.)
    assert "BASE_RENDER_WRONG_VERSION" not in _room_error_details(resp)
    assert "BASE_RENDER_WRONG_ROOM" not in _room_error_details(resp)
    assert "BASE_RENDER_WRONG_SIZE" not in _room_error_details(resp)


# ── stale-after-edit: capture bound to vA rejected once the design is vB ─────────
def test_stale_after_edit_rejected_end_to_end():
    project = client.post("/api/projects", json={"name": "__h12_stale__", "floor_count": 1}).json()
    pid, fid = project["id"], project["floors"][0]["id"]
    try:
        up = client.post(
            "/api/floor-plans/upload",
            files={"file": ("empty.png", BytesIO(PNG_1PX), "image/png")},
            data={"project_id": pid, "floor_id": fid},
        )
        plan_id = up.json()["id"]
        # VERSION A — a bed (eligible for the "Bedroom 1" section so a room is built).
        client.put(f"/api/floor-plans/{plan_id}/layout", json={"items": [
            {"uid": "bed-1", "item_id": "bed", "cx": 500, "cy": 350, "w": 1800, "h": 2000, "rotation": 0},
        ]})
        version_a = client.get(f"/api/floor-plans/{plan_id}/scene").json()["design_version_id"]
        # VERSION B (user moved the bed after capturing A)
        client.put(f"/api/floor-plans/{plan_id}/layout", json={"items": [
            {"uid": "bed-1", "item_id": "bed", "cx": 900, "cy": 700, "w": 1800, "h": 2000, "rotation": 0},
        ]})
        version_b = client.get(f"/api/floor-plans/{plan_id}/scene").json()["design_version_id"]
        assert version_a != version_b

        # Generate with the STALE version-A metadata while the design is now B.
        boom = mock.MagicMock(side_effect=AssertionError("fal network call attempted"))
        adapter = FalFluxAdapter()
        adapter.api_key = "test-key"
        adapter.arbitrary_image_effective = True
        meta = {"Bedroom 1": {"design_version_id": version_a, "room_key": "Bedroom 1",
                              "width": 1216, "height": 832}}
        with mock.patch.object(registry, "get_adapter", return_value=adapter), \
             mock.patch.object(generation_service, "AI_DEMO_MODE", False), \
             mock.patch.object(fal_flux_adapter.httpx, "Client", boom):
            resp = generation_service.generate(
                file_id=plan_id, provider="fal", count=1,
                design_intent={"style": "Modern"}, requested_rooms=["Bedroom 1"],
                fresh_generation=True,
                base_renders={"Bedroom 1": _png_dataurl()},
                base_render_meta=meta,
            )
        assert "BASE_RENDER_WRONG_VERSION" in _room_error_details(resp)
        boom.assert_not_called()  # the stale base render never reached fal
    finally:
        client.delete(f"/api/projects/{pid}")
