"""Offline tests for Path B geometry conditioning (opt-in structural control image).

No fal/paid calls. Verifies: baseline request unchanged when disabled, structural control
used only when the flag is on AND a structural image is supplied, only documented fields are
emitted, and the snapshot-bound pair validator rejects mismatched/missing pairs.
"""

from unittest import mock

from app.services import structural_pair as sp
from app.services.ai.base import GenerationRequest
from app.services.ai.fal_flux_adapter import FalFluxAdapter

_ADAPTER = "app.services.ai.fal_flux_adapter"
# Documented (fal) + existing-adapter fields. No NEW field is introduced by Path B.
_ALLOWED_CONTROL_KEYS = {
    "prompt", "control_lora_image_url", "control_lora_strength", "num_images",
    "output_format", "image_url", "image_size", "seed", "guidance_scale", "num_inference_steps",
}
_ALLOWED_EDIT_KEYS = {"prompt", "image_url", "num_images", "output_format", "seed",
                      "guidance_scale", "num_inference_steps"}

BASE = "data:image/png;base64,QkFTRQ=="       # "BASE"
STRUCT = "data:image/png;base64,U1RSVUNU"     # "STRUCT"


def _req() -> GenerationRequest:
    return GenerationRequest(prompt="ROOM: Bedroom 1.\nINVENTORY: bed.", style=None, count=1,
                             width=1216, height=832, seed=7,
                             control_image=b"base-bytes", structural_image=b"struct-bytes")


# ── config default is opt-in/off ───────────────────────────────────────────────────
def test_structural_flag_defaults_off():
    from app.core import config
    assert config.FAL_CONTROL_STRUCTURAL is False


# ── edit baseline unchanged, even if a structural image is on the request ──────────
def test_edit_body_ignores_structural_image():
    body = FalFluxAdapter()._build_body(_req(), BASE)
    assert set(body).issubset(_ALLOWED_EDIT_KEYS)
    assert body["image_url"] == BASE
    assert "control_lora_image_url" not in body


# ── control path: flag OFF → control is the BASE render (baseline unchanged) ───────
def test_control_body_uses_base_when_flag_off():
    with mock.patch(f"{_ADAPTER}.FAL_CONTROL_STRUCTURAL", False):
        a = FalFluxAdapter()
        body = a._build_control_body(_req(), BASE, 1216, 832, STRUCT)
    assert body["control_lora_image_url"] == BASE          # structural NOT used
    assert body.get("image_url") == BASE
    assert a.last_control_source == "base"
    assert set(body).issubset(_ALLOWED_CONTROL_KEYS)


# ── control path: flag ON + structural present → structural is the control ─────────
def test_control_body_uses_structural_when_enabled():
    with mock.patch(f"{_ADAPTER}.FAL_CONTROL_STRUCTURAL", True):
        a = FalFluxAdapter()
        body = a._build_control_body(_req(), BASE, 1216, 832, STRUCT)
    assert body["control_lora_image_url"] == STRUCT        # STRUCTURE = structural edge map
    assert body.get("image_url") == BASE                   # COLOR init = base render
    assert a.last_control_source == "structural"
    assert set(body).issubset(_ALLOWED_CONTROL_KEYS)        # no unsupported fields


# ── flag ON but NO structural image → falls back to base (fail-safe, not an error) ──
def test_control_body_flag_on_without_structural_uses_base():
    with mock.patch(f"{_ADAPTER}.FAL_CONTROL_STRUCTURAL", True):
        a = FalFluxAdapter()
        body = a._build_control_body(_req(), BASE, 1216, 832, None)
    assert body["control_lora_image_url"] == BASE
    assert a.last_control_source == "base"


# ── model selection is flag-driven, never error/fallback-driven ────────────────────
def test_model_selection_is_flag_driven():
    # The control endpoint/model is chosen from FAL_USE_CONTROLNET, not from any provider
    # response — so an error can never silently switch models.
    with mock.patch(f"{_ADAPTER}.FAL_USE_CONTROLNET", True), \
         mock.patch(f"{_ADAPTER}.FAL_CONTROL_MODEL", "fal-ai/flux-control-lora-canny"):
        a = FalFluxAdapter()
        assert "flux-control-lora-canny" in a._control_endpoint()
    with mock.patch(f"{_ADAPTER}.FAL_USE_CONTROLNET", False):
        a = FalFluxAdapter()
        assert a._endpoint().endswith(a.model)


# ── snapshot-bound pair validation ─────────────────────────────────────────────────
_BASE_META = {"design_version_id": "dv-1", "room_key": "Bedroom 1", "width": 1216, "height": 832,
              "camera": {"fov": 46, "aspect": 1.4615}}


def test_pair_ok_when_version_room_dims_match():
    ok, _ = sp.validate_structural_pair(_BASE_META, dict(_BASE_META))
    assert ok


def test_pair_rejects_version_mismatch():
    s = dict(_BASE_META, design_version_id="dv-2")
    ok, reason = sp.validate_structural_pair(_BASE_META, s)
    assert not ok and "WRONG_VERSION" in reason


def test_pair_rejects_room_mismatch():
    s = dict(_BASE_META, room_key="Kitchen")
    ok, reason = sp.validate_structural_pair(_BASE_META, s)
    assert not ok and "WRONG_ROOM" in reason


def test_pair_rejects_size_mismatch():
    s = dict(_BASE_META, width=64, height=64)
    ok, reason = sp.validate_structural_pair(_BASE_META, s)
    assert not ok and "WRONG_SIZE" in reason


def test_pair_rejects_camera_mismatch():
    s = dict(_BASE_META, camera={"fov": 72, "aspect": 1.4615})
    ok, reason = sp.validate_structural_pair(_BASE_META, s)
    assert not ok and "CAMERA_MISMATCH" in reason


def test_pair_rejects_missing_structural():
    ok, reason = sp.validate_structural_pair(_BASE_META, None)
    assert not ok and "STRUCTURAL_MISSING" in reason


# ── ACTUAL structural control BYTES validation (AUDIT fix) ─────────────────────────
# The pair validator above only inspects DECLARED metadata. The gate additionally proves
# the real structural PNG the model will receive is a decodable image of the expected
# capture size, so a corrupt / wrong-size / missing structural control fails CLOSED before
# any fal call — the base render was already held to this standard; the structural was not.
import io  # noqa: E402

from PIL import Image as _Image  # noqa: E402

from app.services.generation_service import (  # noqa: E402
    _validate_structural_image_bytes as _vsb,
)


def _png(w: int, h: int, color: tuple[int, int, int] = (0, 0, 0)) -> bytes:
    buf = io.BytesIO()
    _Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


def test_structural_bytes_ok_when_dims_match():
    ok, reason = _vsb(_png(1216, 832), 1216, 832)
    assert ok and reason == "OK"


def test_structural_bytes_rejects_corrupt():
    ok, reason = _vsb(b"valid-base64-but-not-an-image", 1216, 832)
    assert not ok and "STRUCTURAL_CORRUPT" in reason


def test_structural_bytes_rejects_wrong_size():
    ok, reason = _vsb(_png(512, 512), 1216, 832)
    assert not ok and "STRUCTURAL_WRONG_SIZE" in reason


def test_structural_bytes_rejects_missing():
    ok, reason = _vsb(None, 1216, 832)
    assert not ok and "STRUCTURAL_MISSING" in reason


def test_structural_bytes_skips_size_when_declared_dims_absent():
    # Base declared no capture dims → size check skipped (opt-in, mirrors the base
    # contract), but decodability is still enforced.
    ok, _ = _vsb(_png(640, 480), None, None)
    assert ok


def test_structural_bytes_accepts_sparse_dark_wireframe():
    # A perspective structural edge map is a sparse line drawing: mostly dark with a few
    # bright edges → very low mean luminance. The base BLANK heuristic (mean < 12) would
    # flag it; proving it is ACCEPTED guards the fix against false-rejecting a valid pass.
    im = _Image.new("RGB", (1216, 832), (0, 0, 0))
    for x in range(0, 1216, 40):
        for y in range(832):
            im.putpixel((x, y), (255, 255, 255))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    ok, reason = _vsb(buf.getvalue(), 1216, 832)
    assert ok and reason == "OK"
