"""Step 2R — offline AI-fidelity conditioning guards (no external calls, no DB writes).

Locks the honest contract exposed by the real fal Kitchen failure (174503c2): an image-EDIT
render WITHOUT structural conditioning must never be reported geometry-FAITHFUL, the adapter's
declared model/mode must match the configured conditioning path, and a control image must be
wired to the structural stage. Mocked adapters / direct function calls only.
"""
from __future__ import annotations

from app.services import validation_service as V


FAITHFUL_SCENE = {"geometry_faithful": True}


# ── assess_ai_render: no geometry-FAITHFUL without structural conditioning ─────

def test_edit_path_cannot_be_faithful_even_if_output_verified():
    # structural_conditioning=False (edit path) -> never FAITHFUL, even with output_verified
    r = V.assess_ai_render(used_base_render=True, scene_report=FAITHFUL_SCENE,
                           output_verified=True, structural_conditioning=False)
    assert r["geometry_status"] == "UNVERIFIED"
    assert r["geometry_faithful"] is None
    assert r["structural_conditioning"] is False


def test_structural_conditioning_allows_faithful_when_output_verified():
    r = V.assess_ai_render(used_base_render=True, scene_report=FAITHFUL_SCENE,
                           output_verified=True, structural_conditioning=True)
    assert r["geometry_status"] == "FAITHFUL"
    assert r["geometry_faithful"] is True


def test_unknown_conditioning_is_backward_compatible():
    # None (legacy/unknown) preserves prior behavior: FAITHFUL possible when output_verified
    r = V.assess_ai_render(used_base_render=True, scene_report=FAITHFUL_SCENE,
                           output_verified=True, structural_conditioning=None)
    assert r["geometry_status"] == "FAITHFUL"


def test_edit_path_unverified_output_is_unverified_not_fail():
    # the real production case: base used, no output check, edit path -> UNVERIFIED
    r = V.assess_ai_render(used_base_render=True, scene_report=FAITHFUL_SCENE,
                           output_verified=False, structural_conditioning=False)
    assert r["geometry_status"] == "UNVERIFIED"


def test_no_base_is_fail_regardless_of_conditioning():
    for sc in (True, False, None):
        r = V.assess_ai_render(used_base_render=False, scene_report=None,
                               output_verified=True, structural_conditioning=sc)
        assert r["geometry_status"] == "FAIL"
        assert r["geometry_faithful"] is False


def test_failed_base_scene_is_fail():
    r = V.assess_ai_render(used_base_render=True, scene_report={"geometry_faithful": False},
                           output_verified=True, structural_conditioning=True)
    assert r["geometry_status"] == "FAIL"


# ── fal adapter: declared model/mode matches the configured conditioning path ──

def _fal():
    from app.services.ai import fal_flux_adapter as FA
    return FA


def test_fal_describe_edit_mode_when_controlnet_off(monkeypatch):
    FA = _fal()
    monkeypatch.setattr(FA, "FAL_USE_CONTROLNET", False, raising=False)
    d = FA.fal_config_summary()
    assert d["conditioning_mode"] == "edit"
    assert d["controlnet_enabled"] is False
    assert d["model"] == FA.FAL_IMAGE_MODEL           # active model is the edit model
    assert "STRUCTURE_LOCK" not in d["model_declared_capabilities"]


def test_fal_describe_controlnet_mode_when_enabled(monkeypatch):
    FA = _fal()
    monkeypatch.setattr(FA, "FAL_USE_CONTROLNET", True, raising=False)
    d = FA.fal_config_summary()
    assert d["conditioning_mode"] == "canny_controlnet"
    assert d["controlnet_enabled"] is True
    assert d["model"] == FA.FAL_CONTROL_MODEL          # active model is the control model
    assert "STRUCTURE_LOCK" in d["model_declared_capabilities"]


def test_fal_control_body_wires_base_to_structural_stage():
    """The control (Canny) body must pass the base as the STRUCTURAL control image, not a
    loose edit reference — i.e. `control_lora_image_url` is present."""
    FA = _fal()
    from app.services.ai.base import GenerationRequest
    adapter = FA.FalFluxAdapter()
    req = GenerationRequest(prompt="preserve furniture", style=None, count=1,
                            width=1216, height=832, seed=7, room_label="Kitchen",
                            control_image=b"\x89PNG\r\n\x1a\n")
    body = adapter._build_control_body(req, "data:image/png;base64,AAAA", 1216, 832)
    assert "control_lora_image_url" in body
    assert body["control_lora_image_url"].startswith("data:image/png;base64,")
