"""Feature-flagged img2img / control-image gating (additive, backward-compatible).

Proves the two-gate contract for the deterministic base render -> NVIDIA request.
img2img is allowed ONLY when NVIDIA_SUPPORTS_IMG2IMG AND
NVIDIA_ARBITRARY_IMAGE_SUPPORTED AND request.control_image is not None; otherwise
the existing text-to-image behavior is preserved and NO invalid image payload is
sent. A failure in img2img mode surfaces the REAL provider error and is never a
silent text-to-image "geometry-faithful" success.

  A  SUPPORTS=false                       -> text-to-image, NO control image sent
  B  SUPPORTS=true, ARBITRARY=true, img   -> control image IN the outgoing body
                                             (image + mode + preprocess_image)
  C  both flags true, control_image=None  -> no image field, no malformed payload
  D  SUPPORTS=true, ARBITRARY=false, img  -> refused up front, NO HTTP request
  E  prompt isolation: _IMG2IMG_PREAMBLE only on the img2img path
  F  generation_service: base_render -> request.control_image -> adapter unchanged
  G  img2img enabled + provider rejects   -> real error surfaced, never a silent
                                             text-to-image fallback claimed faithful

All HTTP is mocked; no real network or self-hosted NIM is required.
"""

import base64
from io import BytesIO
from unittest import mock

import httpx
import pytest
from PIL import Image

from app.services import floor_plan_service, generation_service
from app.services.ai.base import AIProviderAdapter, AIProviderError, GenerationRequest
from app.services.ai.nvidia_flux_adapter import NvidiaFluxAdapter

_MOD = "app.services.ai.nvidia_flux_adapter"


def _png_bytes(color=(200, 180, 150)) -> bytes:
    img = Image.new("RGB", (64, 64), color)
    for y in range(32):
        for x in range(64):
            img.putpixel((x, y), (30, 40, 60))
    buf = BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _resp(status: int, *, json_body=None, text="") -> mock.Mock:
    r = mock.Mock()
    r.status_code = status
    r.json.return_value = json_body if json_body is not None else {}
    r.content = b""
    r.text = text
    r.headers = {}
    r.request = mock.Mock()
    return r


def _artifacts_ok() -> dict:
    return {"artifacts": [{"base64": base64.b64encode(_png_bytes()).decode("ascii")}]}


def _capture_post(captured):
    def _post(url, json=None, headers=None):  # noqa: A002
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _resp(200, json_body=_artifacts_ok())
    return _post


def _t2i_adapter(key="nvapi-secret") -> NvidiaFluxAdapter:
    with mock.patch(f"{_MOD}.NVIDIA_API_KEY", key), \
         mock.patch(f"{_MOD}.NVIDIA_SUPPORTS_IMG2IMG", False):
        return NvidiaFluxAdapter()


# Arbitrary image input is genuinely supported only on a self-hosted NIM (the hosted
# API is example_id-only), so the img2img-send tests point at a NIM base.
_NIM_BASE = "http://nim-host:8000"


def _img2img_adapter(
    mode="canny", key="nvapi-secret", model="black-forest-labs/flux.1-canny-dev",
    base=_NIM_BASE,
) -> NvidiaFluxAdapter:
    # A ControlNet model (canny/depth) on a self-hosted NIM is required for a genuine
    # img2img request; flux.1-dev is text-to-image only, and the hosted API rejects
    # arbitrary images regardless of model.
    with mock.patch(f"{_MOD}.NVIDIA_API_KEY", key), \
         mock.patch(f"{_MOD}.NVIDIA_SUPPORTS_IMG2IMG", True), \
         mock.patch(f"{_MOD}.NVIDIA_IMG2IMG_MODE", mode), \
         mock.patch(f"{_MOD}.NVIDIA_IMAGE_MODEL", model), \
         mock.patch(f"{_MOD}.NVIDIA_API_BASE", base):
        return NvidiaFluxAdapter()


def _req(control=None, prompt="a calm living room"):
    return GenerationRequest(
        prompt=prompt, style=None, count=1, width=1024, height=1024, seed=3,
        control_image=control,
    )


# ── A. Existing mode: SUPPORTS=false -> text-to-image, no control image ────────

def test_A_supports_false_is_text_to_image_no_control():
    a = _t2i_adapter()
    assert a.supports_control_image is False
    assert a.mode == "base"
    captured: dict = {}
    with mock.patch.object(httpx.Client, "post", side_effect=_capture_post(captured)):
        a.generate(_req(control=_png_bytes()))  # base render present but IGNORED
    body = captured["json"]
    assert body["mode"] == "base"
    for forbidden in ("image", "preprocess_image", "canny", "depth", "example_id"):
        assert forbidden not in body, f"text-to-image must not send {forbidden!r}"
    assert body["width"] == 1024 and body["height"] == 1024


# ── B. Img2img mode: both flags true + control image -> image IN the payload ───

def test_B_img2img_sends_control_image_in_outgoing_payload():
    a = _img2img_adapter(mode="canny")
    assert a.supports_control_image is True
    assert a.mode == "canny"
    captured: dict = {}
    with mock.patch(f"{_MOD}.NVIDIA_ARBITRARY_IMAGE_SUPPORTED", True), \
         mock.patch.object(httpx.Client, "post", side_effect=_capture_post(captured)):
        a.generate(_req(control=_png_bytes()))
    body = captured["json"]
    # The ACTUAL outgoing request carries the image (not just a log line).
    assert "image" in body, "img2img request MUST contain the control image"
    assert body["image"].startswith("data:image/png;base64,")
    raw = base64.b64decode(body["image"].split(",", 1)[1])
    assert Image.open(BytesIO(raw)).format == "PNG"  # decodes to a real PNG
    # Conditioning mode + preprocessing present; control dictates aspect (no w/h).
    assert body["mode"] == "canny"
    assert body["preprocess_image"] is True
    assert "width" not in body and "height" not in body
    assert {"prompt", "steps", "cfg_scale", "seed"} <= set(body)


def test_B_depth_mode_uses_depth_conditioning():
    a = _img2img_adapter(mode="depth")
    captured: dict = {}
    with mock.patch(f"{_MOD}.NVIDIA_ARBITRARY_IMAGE_SUPPORTED", True), \
         mock.patch.object(httpx.Client, "post", side_effect=_capture_post(captured)):
        a.generate(_req(control=_png_bytes()))
    assert captured["json"]["mode"] == "depth"
    assert captured["json"]["preprocess_image"] is True
    assert "image" in captured["json"]


# ── C. Both flags true but control_image=None -> no invalid image request ──────

def test_C_both_flags_true_no_control_image_is_safe_text_to_image():
    a = _img2img_adapter()
    captured: dict = {}
    with mock.patch(f"{_MOD}.NVIDIA_ARBITRARY_IMAGE_SUPPORTED", True), \
         mock.patch.object(httpx.Client, "post", side_effect=_capture_post(captured)):
        a.generate(_req(control=None))  # no base render available for this room
    body = captured["json"]
    assert "image" not in body, "must NOT send an image field when none was provided"
    assert body["mode"] == "base"          # falls back to the designed text-to-image body
    assert body["width"] == 1024 and body["height"] == 1024


# ── D. SUPPORTS=true, ARBITRARY=false -> gate refuses, NO HTTP request ─────────

def test_D_arbitrary_disabled_refuses_without_sending():
    a = _img2img_adapter()
    with mock.patch(f"{_MOD}.NVIDIA_ARBITRARY_IMAGE_SUPPORTED", False), \
         mock.patch.object(httpx.Client, "post") as post:
        with pytest.raises(AIProviderError) as ei:
            a.generate(_req(control=_png_bytes()))
    assert ei.value.status_code == 422
    assert "NVIDIA_ARBITRARY_IMAGE_UNSUPPORTED" in str(ei.value)
    post.assert_not_called()  # never sends a doomed/invalid arbitrary-image request


# ── E. Prompt isolation: geometry-lock preamble only on the img2img path ───────

def test_E_preamble_present_only_on_img2img():
    # text-to-image: preamble ABSENT
    t2i = _t2i_adapter()
    cap_t2i: dict = {}
    with mock.patch.object(httpx.Client, "post", side_effect=_capture_post(cap_t2i)):
        t2i.generate(_req(control=_png_bytes(), prompt="a living room"))
    assert "GEOMETRY LOCK" not in cap_t2i["json"]["prompt"].upper()

    # img2img: preamble PRESENT
    i2i = _img2img_adapter()
    cap_i2i: dict = {}
    with mock.patch(f"{_MOD}.NVIDIA_ARBITRARY_IMAGE_SUPPORTED", True), \
         mock.patch.object(httpx.Client, "post", side_effect=_capture_post(cap_i2i)):
        i2i.generate(_req(control=_png_bytes(), prompt="a living room"))
    assert "GEOMETRY LOCK" in cap_i2i["json"]["prompt"].upper()


# ── F. generation_service: base_render -> control_image -> adapter unchanged ───

class _SpyAdapter(AIProviderAdapter):
    name = "nvidia"
    model = "black-forest-labs/flux.1-dev"
    supports_control_image = True

    def __init__(self):
        self.seen_control = "UNSET"

    def generate(self, request: GenerationRequest):
        self.seen_control = request.control_image
        return [_png_bytes()]


_CANONICAL = {
    "furniture": [
        {"uid": "b", "item_id": "bed", "cx": 500, "cy": 350, "w": 1800, "h": 2000, "rotation": 0},
    ]
}


def _run(adapter, *, base_render, scene_faithful):
    return generation_service._render_room(
        adapter, "nvidia", "Modern", ("Bedroom 1", "p", 1024, 768),
        ("proj", "fp", _CANONICAL, None),
        generation_id="g", index=0, seed=1, fresh_generation=True,
        base_render=base_render, scene_geometry_faithful=scene_faithful,
    )


def test_F_base_render_reaches_adapter_as_control_image():
    base = _png_bytes((10, 20, 30))
    spy = _SpyAdapter()
    with mock.patch("app.services.generation_service.AI_DEMO_MODE", False):
        _run(spy, base_render=base, scene_faithful=True)
    # The exact base-render bytes captured by BaseRenderBatch reach the adapter
    # as request.control_image, unchanged — no new capture path was introduced.
    assert spy.seen_control == base


# ── G. No silent fallback: img2img failure surfaces the real provider error ────

class _Img2ImgFailing(AIProviderAdapter):
    """img2img-capable provider whose control-image request is rejected."""

    name = "nvidia"
    model = "black-forest-labs/flux.1-dev"
    supports_control_image = True

    def generate(self, request: GenerationRequest):
        assert request.control_image is not None  # img2img request was attempted
        raise AIProviderError("nvidia", "NIM rejected control image: HTTP 502", 502)


def test_G_img2img_failure_is_real_error_not_silent_text_to_image():
    with mock.patch("app.services.generation_service.AI_DEMO_MODE", False):
        with pytest.raises(floor_plan_service.FloorPlanError) as ei:
            _run(_Img2ImgFailing(), base_render=_png_bytes(), scene_faithful=True)
    # Real provider status preserved; NOT masked, NOT a fabricated success.
    assert ei.value.status_code == 502
    assert "502" in str(ei.value.detail)
    assert "geometry_faithful" not in str(ei.value.detail).lower()


def test_G_adapter_attempts_img2img_then_raises_without_downgrade():
    # At the real adapter: both flags on, NIM returns 422. The adapter must have
    # SENT the image (attempted img2img) and then RAISED — never silently retried
    # a prompt-only text-to-image request.
    a = _img2img_adapter()
    captured: dict = {}

    def _post(url, json=None, headers=None):  # noqa: A002
        captured["json"] = json
        return _resp(422, text="rejected")

    with mock.patch(f"{_MOD}.NVIDIA_ARBITRARY_IMAGE_SUPPORTED", True), \
         mock.patch.object(httpx.Client, "post", side_effect=_post), \
         mock.patch(f"{_MOD}.time.sleep"):
        with pytest.raises(AIProviderError) as ei:
            a.generate(_req(control=_png_bytes()))
    assert ei.value.status_code == 422
    assert "image" in captured["json"], "must have attempted the img2img request"


# ── AI_RENDER_CONFIG safe diagnostic (never leaks key/auth/base64) ─────────────

def test_render_config_diagnostic_is_safe_and_accurate(caplog):
    a = _img2img_adapter(mode="canny", key="nvapi-DIAG-SECRET")
    with mock.patch(f"{_MOD}.NVIDIA_ARBITRARY_IMAGE_SUPPORTED", True), \
         mock.patch.object(httpx.Client, "post",
                           return_value=_resp(200, json_body=_artifacts_ok())), \
         caplog.at_level("INFO", logger="app.services.ai.nvidia_flux"):
        a.generate(_req(control=_png_bytes()))
    line = next(m for m in (r.getMessage() for r in caplog.records)
               if "AI_RENDER_CONFIG" in m)
    assert "img2img_enabled=True" in line
    assert "arbitrary_image_requested=True" in line
    assert "image_input_supported=True" in line      # genuine capability (canny model)
    assert "control_image_present=True" in line
    assert "conditioning_mode=canny" in line
    assert "nvapi-DIAG-SECRET" not in line          # key never logged
    assert "base64" not in line and "data:image" not in line
