"""Durable, byte-accurate conditioning provenance (Arm B vs Arm C distinguishability).

Offline only — no fal/paid call. The adapter HTTP send is mocked. Proves:
  * control_source + control_image_sha256 distinguish base-control from structural-control,
    even though conditioning_mode is identical ("canny_controlnet") for both;
  * hashes are the EXACT submitted/produced bytes (different bytes -> different SHA);
  * endpoint + effective control strength reflect the ACTUAL request, not config intent;
  * missing/edit/legacy/failed cases are represented honestly (no fabricated values);
  * provenance survives the normal on-disk persistence/retrieval path (render_debug.json).
"""

import hashlib
import json
from io import BytesIO

import pytest
from PIL import Image

from app.services import generation_service as gs
from app.services.ai import fal_flux_adapter as FA
from app.services.ai.base import GenerationRequest
from app.services.ai.fal_flux_adapter import FalFluxAdapter


def _png(color: tuple[int, int, int]) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (8, 8), color).save(buf, format="PNG")
    return buf.getvalue()


BASE_PNG = _png((10, 20, 30))
STRUCT_PNG = _png((200, 210, 220))  # visibly different bytes -> different SHA
OUT_PNG = _png((90, 90, 90))


class _Resp:
    status_code = 200
    headers = {"x-fal-request-id": "req-test-123"}
    text = "{}"

    def json(self) -> dict:
        return {"images": [{"url": "http://example.invalid/out.png"}]}


class _Client:
    def __init__(self, *a, **k) -> None:  # noqa: D401
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, json=None, headers=None):  # noqa: A002
        return _Resp()


@pytest.fixture
def adapter(monkeypatch):
    """A FalFluxAdapter whose network send is fully mocked (no real fal call)."""
    monkeypatch.setattr(FA.httpx, "Client", _Client)
    monkeypatch.setattr(FalFluxAdapter, "_resolve_queue", lambda self, payload, *a, **k: payload)
    monkeypatch.setattr(FalFluxAdapter, "_fetch_image", lambda self, *a, **k: OUT_PNG)
    a = FalFluxAdapter()
    a.api_key = "test-key"               # avoid the real-key guard
    a.arbitrary_image_effective = True   # allow the arbitrary-image (control) path
    return a


def _req(structural: bytes | None) -> GenerationRequest:
    return GenerationRequest(
        prompt="ROOM: Bedroom 1.\nINVENTORY: bed.", style=None, count=1,
        width=1216, height=832, seed=7, room_label="Bedroom 1",
        control_image=BASE_PNG, structural_image=structural,
    )


# ── Arm distinction ──────────────────────────────────────────────────────────────────────
def test_arm_b_base_control_records_control_source_base(adapter, monkeypatch):
    monkeypatch.setattr(FA, "FAL_USE_CONTROLNET", True, raising=False)
    monkeypatch.setattr(FA, "FAL_CONTROL_STRUCTURAL", False, raising=False)
    adapter.generate(_req(structural=None))
    assert adapter.last_conditioning_mode == "canny_controlnet"
    assert adapter.last_control_source == "base"
    assert adapter.last_control_image_sha256 == hashlib.sha256(FA._to_png(BASE_PNG)).hexdigest()
    assert adapter.last_structural_image_sha256 is None


def test_arm_c_structural_control_records_control_source_structural(adapter, monkeypatch):
    monkeypatch.setattr(FA, "FAL_USE_CONTROLNET", True, raising=False)
    monkeypatch.setattr(FA, "FAL_CONTROL_STRUCTURAL", True, raising=False)
    adapter.generate(_req(structural=STRUCT_PNG))
    assert adapter.last_conditioning_mode == "canny_controlnet"
    assert adapter.last_control_source == "structural"
    # The control image is the STRUCTURAL edge map, not the base.
    struct_sha = hashlib.sha256(FA._to_png(STRUCT_PNG)).hexdigest()
    assert adapter.last_control_image_sha256 == struct_sha
    assert adapter.last_structural_image_sha256 == struct_sha


def test_same_conditioning_mode_but_distinguishable_arms(adapter, monkeypatch):
    monkeypatch.setattr(FA, "FAL_USE_CONTROLNET", True, raising=False)
    monkeypatch.setattr(FA, "FAL_CONTROL_STRUCTURAL", False, raising=False)
    adapter.generate(_req(structural=None))
    b_mode = adapter.last_conditioning_mode
    b_src = adapter.last_control_source
    b_ctrl = adapter.last_control_image_sha256
    monkeypatch.setattr(FA, "FAL_CONTROL_STRUCTURAL", True, raising=False)
    adapter.generate(_req(structural=STRUCT_PNG))
    c_mode = adapter.last_conditioning_mode
    c_src = adapter.last_control_source
    c_ctrl = adapter.last_control_image_sha256
    assert b_mode == c_mode == "canny_controlnet"   # identical mode...
    assert b_src == "base" and c_src == "structural"  # ...but distinguishable source...
    assert b_ctrl != c_ctrl                            # ...and different control-image bytes.


# ── Edit baseline (Arm A) + endpoint + strength ─────────────────────────────────────────
def test_arm_a_edit_has_no_control_provenance(adapter, monkeypatch):
    monkeypatch.setattr(FA, "FAL_USE_CONTROLNET", False, raising=False)
    adapter.generate(_req(structural=None))
    assert adapter.last_conditioning_mode == "edit"
    assert adapter.last_control_source is None
    assert adapter.last_control_image_sha256 is None
    assert adapter.last_structural_image_sha256 is None
    assert adapter.last_control_strength is None
    assert adapter.model in adapter.last_endpoint  # edit endpoint = the edit model route


def test_endpoint_and_strength_reflect_actual_request(adapter, monkeypatch):
    monkeypatch.setattr(FA, "FAL_USE_CONTROLNET", True, raising=False)
    monkeypatch.setattr(FA, "FAL_CONTROL_STRUCTURAL", True, raising=False)
    monkeypatch.setattr(FA, "FAL_CONTROL_STRENGTH", 0.7, raising=False)
    adapter.generate(_req(structural=STRUCT_PNG))
    assert FA.FAL_CONTROL_MODEL in adapter.last_endpoint       # canny control route
    assert adapter.last_control_strength == 0.7                # effective submitted value


def test_strength_default_applied_when_unset(adapter, monkeypatch):
    monkeypatch.setattr(FA, "FAL_USE_CONTROLNET", True, raising=False)
    monkeypatch.setattr(FA, "FAL_CONTROL_STRUCTURAL", False, raising=False)
    monkeypatch.setattr(FA, "FAL_CONTROL_STRENGTH", None, raising=False)
    adapter.generate(_req(structural=None))
    assert adapter.last_control_strength == 1.0                # default, post-application


# ── Durable persistence + retrieval (render_debug.json), legacy + failure honesty ────────
def _write_and_read(tmp_path, monkeypatch, **kw) -> dict:
    monkeypatch.setattr(gs, "DEBUG_ARTIFACTS_DIR", tmp_path)
    gs._save_debug_artifacts(
        "gen-xyz", 0, "Bedroom 1", "prompt", "fal", "fal-ai/flux-control-lora-canny",
        1216, 832, kw.pop("status", "success"), **kw,
    )
    p = tmp_path / "gen-xyz" / "room_0_Bedroom 1" / "render_debug.json"
    return json.loads(p.read_text(encoding="utf-8"))


def test_provenance_persists_and_reads_back(tmp_path, monkeypatch):
    rec = _write_and_read(
        tmp_path, monkeypatch,
        control_source="structural", control_image_sha256="aaa", structural_image_sha256="aaa",
        control_strength=1.0, endpoint="https://queue.fal.run/fal-ai/flux-control-lora-canny",
        output_image_sha256="ddd",
    )
    assert rec["control_source"] == "structural"
    assert rec["control_image_sha256"] == "aaa"
    assert rec["output_image_sha256"] == "ddd"
    assert "flux-control-lora-canny" in rec["endpoint"]


def test_failed_render_has_no_fabricated_output_hash(tmp_path, monkeypatch):
    rec = _write_and_read(
        tmp_path, monkeypatch, status="failed", error="boom",
        control_source="base", control_image_sha256="bbb",
    )
    assert rec["control_source"] == "base"
    assert rec["output_image_sha256"] is None  # never fabricated on failure


def test_legacy_record_without_new_fields_is_readable(tmp_path, monkeypatch):
    # A record written WITHOUT the new provenance (older generation) still reads cleanly;
    # the new fields are simply absent/None (backward compatible, mirrors _image_response).
    rec = _write_and_read(tmp_path, monkeypatch, seed=7)
    assert rec.get("control_source") is None
    assert rec.get("output_image_sha256") is None
    assert rec["seed"] == 7  # existing fields unaffected
