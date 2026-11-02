"""AIR-08 provenance: persist the ACTUAL output image dimensions and the fal request id.

Covers: _png_dims derives real dimensions; the fal adapter exposes last_request_id on
success (and None when the header is absent / on failure); _save_debug_artifacts persists
output_width/output_height/provider_request_id into provider_response_metadata.json while
preserving the existing fields; and a missing request id is handled safely.
"""

import base64
import io
import json
import uuid
from unittest import mock

import httpx
import pytest
from PIL import Image

from app.core.config import DEBUG_ARTIFACTS_DIR
from app.services import generation_service as GS
from app.services.ai.base import AIProviderError, GenerationRequest
from app.services.ai.fal_flux_adapter import FalFluxAdapter

_MOD = "app.services.ai.fal_flux_adapter"


def _png(w=640, h=480, color=(123, 200, 90)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


def _resp(status, *, json_body=None, headers=None):
    r = mock.Mock()
    r.status_code = status
    r.json.return_value = json_body if json_body is not None else {}
    r.content = b""
    r.text = ""
    r.headers = headers or {}
    return r


def _adapter():
    with mock.patch(f"{_MOD}.FAL_KEY", "fal-secret"), \
         mock.patch(f"{_MOD}.FAL_API_BASE", "https://fal.run"), \
         mock.patch(f"{_MOD}.FAL_IMAGE_MODEL", "fal-ai/flux-kontext/dev"), \
         mock.patch(f"{_MOD}.FAL_IMAGE_EDIT_SUPPORTED", True), \
         mock.patch(f"{_MOD}.FAL_ARBITRARY_IMAGE_SUPPORTED", True):
        return FalFluxAdapter()


def _req(control=None):
    return GenerationRequest(prompt="restyle, keep geometry", style=None, count=1,
                             width=1024, height=1024, seed=7, control_image=control)


def _success_resp(request_id=None):
    data_uri = "data:image/png;base64," + base64.b64encode(_png()).decode()
    headers = {"x-fal-request-id": request_id} if request_id else {}
    return _resp(200, json_body={"images": [{"url": data_uri}]}, headers=headers)


# ── _png_dims ─────────────────────────────────────────────────────────────────

def test_png_dims_returns_actual_dimensions():
    assert GS._png_dims(_png(800, 600)) == (800, 600)


def test_png_dims_safe_on_none_and_garbage():
    assert GS._png_dims(None) == (None, None)
    assert GS._png_dims(b"not-an-image") == (None, None)


# ── fal adapter last_request_id ───────────────────────────────────────────────

def test_fal_last_request_id_set_on_success():
    a = _adapter()
    with mock.patch.object(httpx.Client, "post", return_value=_success_resp("req-abc-123")):
        out = a.generate(_req(control=_png()))
    assert out and out[0]
    assert a.last_request_id == "req-abc-123"


def test_fal_last_request_id_none_when_header_absent():
    a = _adapter()
    with mock.patch.object(httpx.Client, "post", return_value=_success_resp(None)):
        a.generate(_req(control=_png()))
    assert a.last_request_id is None


def test_fal_last_request_id_reset_on_failure():
    a = _adapter()
    a.last_request_id = "stale-from-a-previous-room"
    locked = _resp(403, json_body={"detail": "User is locked. Reason: TOP_UP."})
    with mock.patch.object(httpx.Client, "post", return_value=locked):
        with pytest.raises(AIProviderError):
            a.generate(_req(control=_png()))
    # reset at the start of generate(), never set on failure
    assert a.last_request_id is None


# ── _save_debug_artifacts persistence ─────────────────────────────────────────

def _read_resp_meta(generation_id, index, label):
    room_dir = DEBUG_ARTIFACTS_DIR / generation_id / f"room_{index}_{label}"
    return json.loads((room_dir / "provider_response_metadata.json").read_text(encoding="utf-8"))


def test_save_debug_artifacts_persists_output_dims_and_request_id():
    gid = f"air08-{uuid.uuid4().hex[:12]}"
    GS._save_debug_artifacts(
        gid, 0, "Bedroom 1", "a prompt", "fal", "fal-ai/flux-kontext/dev", 1216, 832,
        "success", seed=7,
        output_width=1024, output_height=688, provider_request_id="req-xyz",
    )
    meta = _read_resp_meta(gid, 0, "Bedroom 1")
    assert meta["output_width"] == 1024
    assert meta["output_height"] == 688
    assert meta["provider_request_id"] == "req-xyz"
    # existing fields preserved
    assert meta["status"] == "success"
    assert meta["seed"] == 7
    assert meta["cache_hit"] is False
    assert "timestamp" in meta


def test_save_debug_artifacts_missing_request_id_is_safe():
    gid = f"air08-{uuid.uuid4().hex[:12]}"
    # No AIR-08 kwargs supplied at all (legacy caller) — must not error; fields default None.
    GS._save_debug_artifacts(
        gid, 1, "Kitchen", "p", "fal", "m", 1216, 832, "failed", "some provider error", seed=3,
    )
    meta = _read_resp_meta(gid, 1, "Kitchen")
    assert meta["output_width"] is None
    assert meta["output_height"] is None
    assert meta["provider_request_id"] is None
    assert meta["status"] == "failed"
    assert meta["error"] == "some provider error"
