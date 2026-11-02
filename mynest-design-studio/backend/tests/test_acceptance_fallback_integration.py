"""Acceptance / fallback decision — the advisory furniture assessment must NEVER gate a
render, never mark an output FAITHFUL, and must be recorded in provenance reflecting the
manifest reconciliation.

These drive the REAL production caller ``generation_service._render_room`` directly (no DB,
no network, no provider cost — a spy adapter returns a fixed PNG). They lock the Section-6
contract: the detector-based assessment is advisory and non-gating; hard acceptance is the
deterministic gates; a manifest↔evidence mismatch degrades the advisory result to
NOT_VALIDATABLE (never a false pass) WITHOUT failing the render; nothing here is FAITHFUL.
"""
from __future__ import annotations

import json
from io import BytesIO
from unittest import mock

from PIL import Image

from app.services import generation_service
from app.services.ai.base import AIProviderAdapter, GenerationRequest


def _png(color=(200, 180, 150)) -> bytes:
    img = Image.new("RGB", (64, 64), color)
    for y in range(32):
        for x in range(64):
            img.putpixel((x, y), (30, 40, 60))  # a band so it is not blank / not a base clone
    buf = BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


class _SpyAdapter(AIProviderAdapter):
    name = "nvidia"
    model = "black-forest-labs/flux.1-dev"
    supports_control_image = True

    def generate(self, request: GenerationRequest):
        return [_png()]


_CANONICAL = {"furniture": [
    {"uid": "b", "item_id": "bed", "cx": 500, "cy": 350, "w": 1800, "h": 2000, "rotation": 0},
]}


def _run(gen_id, base_boxes, meta_version):
    """Render Bedroom 1 via the real caller; return the persisted render_debug.json dict."""
    base_render = _png((10, 20, 30))  # differs from the adapter output (passes the no-op gate)
    meta = {"Bedroom 1": {"design_version_id": meta_version, "width": 64, "height": 64}}
    with mock.patch("app.services.generation_service.AI_DEMO_MODE", False):
        res = generation_service._render_room(
            _SpyAdapter(), "nvidia", "Modern", ("Bedroom 1", "p", 64, 64),
            ("proj", "fp", _CANONICAL, None),
            generation_id=gen_id, index=0, seed=1, fresh_generation=True,
            base_render=base_render, scene_geometry_faithful=True,
            design_version_id="v1",
            base_boxes=base_boxes, base_render_meta=meta,
        )
    label, png = res[0], res[1]
    assert label == "Bedroom 1" and isinstance(png, (bytes, bytearray)) and png  # render SUCCEEDED
    dbg_path = generation_service.DEBUG_ARTIFACTS_DIR / gen_id / "room_0_Bedroom 1" / "render_debug.json"
    return json.loads(dbg_path.read_text(encoding="utf-8"))


def test_manifest_mismatch_evidence_does_not_fail_render_but_degrades_to_not_validatable():
    # base-render evidence describes a different furniture set than the manifest (bed `b`)
    mismatch_boxes = {"Bedroom 1": [
        {"uid": "x", "item_id": "side-table", "x": 10, "y": 10, "width": 40, "height": 40},
    ]}
    dbg = _run("acc-mismatch", mismatch_boxes, meta_version="v1")
    oia = dbg["output_inventory_assessment"]
    # advisory, non-gating: the render still succeeded (asserted in _run); the assessment
    # honestly reports it cannot validate because evidence != manifest.
    assert oia["overall_status"] == "NOT_VALIDATABLE"
    assert "EVIDENCE_MANIFEST_MISMATCH" in oia["reason"]
    assert oia["manifest_reconciliation"]["status"] in ("MISMATCH", "AMBIGUOUS")
    # provenance binding is attached so the assessment is tied to this version/room
    assert oia["manifest_binding"]["design_version_id"] == "v1"
    assert oia["expected_inventory"]["furniture_count"] == 1
    # NEVER faithful (no output verification ran)
    assert dbg["geometry_status"] != "FAITHFUL"
    assert dbg["geometry_faithful"] is not True


def test_matching_evidence_without_detector_is_not_validatable_never_faithful():
    match_boxes = {"Bedroom 1": [
        {"uid": "b", "item_id": "bed", "x": 10, "y": 10, "width": 40, "height": 40},
    ]}
    dbg = _run("acc-match", match_boxes, meta_version="v1")
    oia = dbg["output_inventory_assessment"]
    assert oia["manifest_reconciliation"]["status"] == "MATCH"
    # evidence matches the manifest, but with no detector the OUTPUT cannot be validated
    assert oia["overall_status"] == "NOT_VALIDATABLE"
    assert "no output detector" in oia["reason"]
    assert oia["calibration_status"] == "NOT_CALIBRATED"
    assert dbg["geometry_status"] != "FAITHFUL"


def test_version_binding_enforced_missing_declared_version_is_not_validatable():
    # expected version is "v1" (passed by the caller) but the evidence declares none
    boxes = {"Bedroom 1": [
        {"uid": "b", "item_id": "bed", "x": 10, "y": 10, "width": 40, "height": 40},
    ]}
    dbg = _run("acc-nover", boxes, meta_version=None)
    oia = dbg["output_inventory_assessment"]
    assert oia["overall_status"] == "NOT_VALIDATABLE"
    assert oia["reason"] == "MISSING_DECLARED_VERSION"
    assert dbg["geometry_status"] != "FAITHFUL"
