"""Deterministic post-AI reject gate (diagram stage: VALIDATE AGAINST 2D/3D SOURCE
-> PASS/FAIL). The AI OUTPUT is compared to the deterministic base render and
REJECTED on blank/degenerate output, aspect-ratio divergence, or a restyle no-op
(~identical to base). No vision detector; no fal call. Rejected renders are never
saved and never fabricated.
"""

from io import BytesIO
from unittest import mock

import pytest
from PIL import Image, ImageDraw

from app.services import floor_plan_service, generation_service as gs
from app.services import validation_service as vs
from app.services.ai.base import AIProviderError, GenerationRequest
from app.services.ai.mock_adapter import MockAdapter


def _structured(w=1216, h=832, base_color=(180, 160, 140), accent=(40, 60, 90)) -> bytes:
    im = Image.new("RGB", (w, h), base_color)
    d = ImageDraw.Draw(im)
    d.rectangle([w * 0.1, h * 0.1, w * 0.6, h * 0.8], fill=accent)
    d.rectangle([w * 0.65, h * 0.3, w * 0.9, h * 0.7], fill=(200, 120, 80))
    for i in range(0, w, 40):
        d.line([(i, 0), (i, h)], fill=(90, 90, 90))
    buf = BytesIO(); im.save(buf, "PNG"); return buf.getvalue()


def _solid(w=1216, h=832, c=(10, 10, 10)) -> bytes:
    buf = BytesIO(); Image.new("RGB", (w, h), c).save(buf, "PNG"); return buf.getvalue()


# ── unit: assess_ai_output_geometry ─────────────────────────────────────────────

def test_valid_restyle_passes():
    base = _structured()
    restyled = _structured(accent=(10, 120, 40), base_color=(240, 230, 210))  # same layout, new palette
    r = vs.assess_ai_output_geometry(restyled, base)
    assert r["passed"] is True
    assert r["mean_abs_diff"] is not None and r["mean_abs_diff"] >= 2.0


def test_blank_output_rejected():
    r = vs.assess_ai_output_geometry(_solid(), _structured())
    assert r["passed"] is False and r["error_code"] == "FAILED_GEOMETRY_VALIDATION"
    assert "blank" in r["reason"].lower()


def test_aspect_divergence_rejected():
    base = _structured(1216, 832)
    square = _structured(832, 832)  # aspect 1.0 vs 1.46 -> diverged
    r = vs.assess_ai_output_geometry(square, base)
    assert r["passed"] is False and r["error_code"] == "FAILED_GEOMETRY_VALIDATION"
    assert "aspect" in r["reason"].lower()


def test_identical_output_rejected_as_no_restyle():
    base = _structured()
    r = vs.assess_ai_output_geometry(base, base)  # byte-identical -> diff 0
    assert r["passed"] is False and r["error_code"] == "FAILED_GEOMETRY_VALIDATION"
    assert "identical" in r["reason"].lower() or "no restyle" in r["reason"].lower()


def test_no_base_only_blank_check():
    # Text-to-image (no base): a valid image passes; a blank one is still rejected.
    assert vs.assess_ai_output_geometry(_structured(), None)["passed"] is True
    assert vs.assess_ai_output_geometry(_solid(), None)["passed"] is False


def test_undecodable_output_rejected():
    r = vs.assess_ai_output_geometry(b"not-an-image", _structured())
    assert r["passed"] is False and r["error_code"] == "FAILED_GEOMETRY_VALIDATION"


# ── integration: _render_room rejects a degenerate AI output (not saved) ────────

FID = "f6b65d2b-4f96-4931-9f08-67dbd09776f6"


class _EchoAdapter(MockAdapter):
    """img2img provider that returns its input base render unchanged (restyle no-op)."""
    supports_control_image = True

    def __init__(self, out: bytes):
        self._out = out

    def generate(self, request: GenerationRequest):
        return [self._out]


class _RestyleAdapter(MockAdapter):
    supports_control_image = True

    def __init__(self, out: bytes):
        self._out = out

    def generate(self, request: GenerationRequest):
        return [self._out]


def _run(adapter, base):
    canonical = floor_plan_service.get_canonical(FID)
    return gs._render_room(
        adapter, "fal", "Modern", ("Living Area", "restyle this living area", 1024, 768),
        ("proj", FID, canonical, None),
        generation_id="g", index=0, seed=1, fresh_generation=True,
        base_render=base, scene_geometry_faithful=True,
    )


def test_render_room_rejects_identical_ai_output():
    base = _structured()
    with mock.patch("app.services.generation_service.AI_DEMO_MODE", False):
        with pytest.raises(floor_plan_service.FloorPlanError) as ei:
            _run(_EchoAdapter(base), base)  # output == base -> restyle no-op
    assert ei.value.status_code == 422
    assert "FAILED_GEOMETRY_VALIDATION" in str(ei.value.detail)


def test_render_room_accepts_valid_restyle():
    base = _structured()
    good = _structured(accent=(10, 120, 40), base_color=(245, 235, 215))  # same geometry, new palette
    with mock.patch("app.services.generation_service.AI_DEMO_MODE", False):
        label, png, provider, model, *_ = _run(_RestyleAdapter(good), base)
    assert label == "Living Area"
    assert Image.open(BytesIO(png)).format == "PNG"
