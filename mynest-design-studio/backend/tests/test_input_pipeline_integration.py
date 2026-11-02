"""Offline INTEGRATION test: Canvas base + structural images → backend decode/validate →
``GenerationRequest`` → fal Canny Control-LoRA request body, with SHA-256 provenance that
matches the ACTUAL submitted bytes.

No fal/paid call — the HTTP boundary is fully mocked and the request body the adapter would
send is CAPTURED and asserted field-by-field. This proves the Definition of Done: the exact
base and structural bytes captured from the Canvas reach the correct fal request fields
(``image_url`` = base render, ``control_lora_image_url`` = structural edge map), the recorded
provenance hashes equal the bytes actually sent, there is no silent fallback to base-only
conditioning, and a pre-dispatch validation failure never reaches the provider.
"""

import base64
import hashlib
from io import BytesIO

import pytest
from PIL import Image

from app.services import generation_service as gs
from app.services.ai import fal_flux_adapter as FA
from app.services.ai.base import AIProviderError, GenerationRequest
from app.services.ai.fal_flux_adapter import FalFluxAdapter

# fal control body: documented + existing-adapter fields only — Path B adds NO new field.
_ALLOWED_CONTROL_KEYS = {
    "prompt", "control_lora_image_url", "control_lora_strength", "num_images",
    "output_format", "image_url", "image_size", "seed", "guidance_scale", "num_inference_steps",
}


def _png(color: tuple[int, int, int]) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (1216, 832), color).save(buf, format="PNG")
    return buf.getvalue()


BASE_PNG = _png((12, 34, 56))
STRUCT_PNG = _png((210, 220, 230))  # visibly different bytes → different SHA
OUT_PNG = _png((99, 99, 99))


def _data_url(png: bytes) -> str:
    """Serialize a capture the way the frontend Canvas does (PNG data URL)."""
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _decode_field(data_url: str) -> bytes:
    """Decode the bytes the adapter actually placed in a request field."""
    return base64.b64decode(data_url.split(",", 1)[1])


class _Resp:
    status_code = 200
    headers = {"x-fal-request-id": "req-int-1"}
    text = "{}"

    def json(self) -> dict:
        return {"images": [{"url": "http://example.invalid/out.png"}]}


class _CapturingClient:
    """Mocked httpx.Client that CAPTURES the request body instead of sending it."""

    posted: list[dict] = []

    def __init__(self, *a, **k) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, json=None, headers=None):  # noqa: A002
        _CapturingClient.posted.append({"url": url, "body": json})
        return _Resp()


@pytest.fixture
def adapter(monkeypatch):
    """A FalFluxAdapter whose network send is mocked and whose request body is captured."""
    _CapturingClient.posted = []
    monkeypatch.setattr(FA.httpx, "Client", _CapturingClient)
    monkeypatch.setattr(FalFluxAdapter, "_resolve_queue", lambda self, payload, *a, **k: payload)
    monkeypatch.setattr(FalFluxAdapter, "_fetch_image", lambda self, *a, **k: OUT_PNG)
    monkeypatch.setattr(FA, "FAL_CONTROL_USE_INIT", True, raising=False)
    a = FalFluxAdapter()
    a.api_key = "test-key"               # avoid the real-key guard
    a.arbitrary_image_effective = True   # allow the arbitrary-image (control) path
    return a


def _req(base: bytes | None, struct: bytes | None) -> GenerationRequest:
    return GenerationRequest(
        prompt="ROOM: Bedroom 1.\nINVENTORY: bed.", style=None, count=1,
        width=1216, height=832, seed=7, room_label="Bedroom 1",
        control_image=base, structural_image=struct,
    )


# ── Canvas serialization ↔ backend decode round-trips the EXACT bytes ──────────────────
def test_canvas_data_url_decodes_to_exact_bytes():
    assert gs._decode_base_render(_data_url(BASE_PNG)) == BASE_PNG
    assert gs._decode_base_render(_data_url(STRUCT_PNG)) == STRUCT_PNG


# ── backend byte-validation accepts the matching pair, rejects invalid (→ no dispatch) ──
def test_backend_validates_actual_structural_bytes():
    assert gs._validate_structural_image_bytes(STRUCT_PNG, 1216, 832)[0] is True
    assert not gs._validate_structural_image_bytes(_png((0, 0, 0))[:40], 1216, 832)[0]  # corrupt
    assert not gs._validate_structural_image_bytes(STRUCT_PNG, 512, 512)[0]            # wrong size


# ── Arm C: structural conditioning → EXACT field mapping + provenance == submitted bytes ─
def test_arm_c_exact_field_mapping_and_provenance(adapter, monkeypatch):
    monkeypatch.setattr(FA, "FAL_USE_CONTROLNET", True, raising=False)
    monkeypatch.setattr(FA, "FAL_CONTROL_STRUCTURAL", True, raising=False)
    base = gs._decode_base_render(_data_url(BASE_PNG))
    struct = gs._decode_base_render(_data_url(STRUCT_PNG))

    out = adapter.generate(_req(base, struct))
    assert len(out) == 1  # a real PNG came back; no fabrication path

    sent = _CapturingClient.posted[-1]
    body = sent["body"]
    # Endpoint = the configured Canny control endpoint (no silent switch).
    assert FA.FAL_CONTROL_MODEL in sent["url"]
    assert sent["url"] == adapter.last_endpoint
    # EXACT field mapping: base render = color init, structural edge map = structure control.
    base_in_body = _decode_field(body["image_url"])
    control_in_body = _decode_field(body["control_lora_image_url"])
    assert base_in_body == FA._to_png(base)
    assert control_in_body == FA._to_png(struct)
    assert base_in_body != control_in_body
    # Provenance hashes equal the bytes ACTUALLY sent (not config intent).
    assert adapter.last_control_source == "structural"
    assert adapter.last_control_image_sha256 == hashlib.sha256(control_in_body).hexdigest()
    assert adapter.last_structural_image_sha256 == hashlib.sha256(control_in_body).hexdigest()
    assert adapter.last_control_strength == body["control_lora_strength"]
    # No unsupported field is submitted.
    assert set(body).issubset(_ALLOWED_CONTROL_KEYS)


# ── Arm B: structural flag OFF → control image is the BASE render (no silent structural) ─
def test_arm_b_base_control_when_structural_disabled(adapter, monkeypatch):
    monkeypatch.setattr(FA, "FAL_USE_CONTROLNET", True, raising=False)
    monkeypatch.setattr(FA, "FAL_CONTROL_STRUCTURAL", False, raising=False)
    base = gs._decode_base_render(_data_url(BASE_PNG))
    # The service passes structural_render=None when structural conditioning is disabled.
    adapter.generate(_req(base, None))

    body = _CapturingClient.posted[-1]["body"]
    assert _decode_field(body["control_lora_image_url"]) == FA._to_png(base)  # base, not structural
    assert adapter.last_control_source == "base"
    assert adapter.last_control_image_sha256 == hashlib.sha256(FA._to_png(base)).hexdigest()
    assert adapter.last_structural_image_sha256 is None  # none supplied → honestly absent


# ── No provider call after a pre-dispatch validation guard fails ───────────────────────
def test_no_provider_call_when_image_edit_disabled(adapter, monkeypatch):
    monkeypatch.setattr(FA, "FAL_USE_CONTROLNET", True, raising=False)
    adapter.arbitrary_image_effective = False  # edit/arbitrary-image capability disabled
    with pytest.raises(AIProviderError):
        adapter.generate(_req(BASE_PNG, STRUCT_PNG))
    assert _CapturingClient.posted == []  # nothing was sent to fal


# ── Failure/timeout: raise a structured error, return no image, fabricate nothing ──────
def test_timeout_raises_504_and_sends_no_image(adapter, monkeypatch):
    monkeypatch.setattr(FA, "FAL_USE_CONTROLNET", True, raising=False)
    monkeypatch.setattr(FA, "FAL_CONTROL_STRUCTURAL", True, raising=False)
    monkeypatch.setattr(FA, "FAL_SINGLE_ATTEMPT", True, raising=False)  # one attempt, no retries

    class _TimeoutClient(_CapturingClient):
        def post(self, url, json=None, headers=None):  # noqa: A002
            raise FA.httpx.TimeoutException("fal slow")

    monkeypatch.setattr(FA.httpx, "Client", _TimeoutClient)
    with pytest.raises(AIProviderError) as ei:
        adapter.generate(_req(BASE_PNG, STRUCT_PNG))
    assert ei.value.status_code == 504
