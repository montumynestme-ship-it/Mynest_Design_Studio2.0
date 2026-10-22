"""Phase 4C Step 1F — surface the existing post-generation LOW_FIDELITY status.

The near-clone detection (postgen_status="LOW_FIDELITY" when mean_abs_diff < 4.0) was
previously recorded only in debug artifacts and NOT returned to the caller. These tests
lock the additive, backward-compatible surfacing:
  * postgen_status is persisted into the authoritative per-render record (render_debug.json,
    the SAME record geometry_status is written to and read from) and surfaced in
    GenerationImageResponse via _image_response;
  * it is independent of geometry_status (LOW_FIDELITY never implies FAITHFUL);
  * a missing/unknown status is None (safe, backward-compatible).
"""

import json
from io import BytesIO
from types import SimpleNamespace
from unittest import mock

from PIL import Image

from app.services import generation_service as G
from app.services.ai.base import AIProviderAdapter


def _solid_png(rgb, size=(128, 128)) -> bytes:
    b = BytesIO()
    Image.new("RGB", size, rgb).save(b, "PNG")
    return b.getvalue()


def _img(label="Kitchen", idx=1):
    return SimpleNamespace(id="img1", image_url="/x", label=label,
                           design_index=idx, total_designs=1)


def _resp(dbg):
    gen = SimpleNamespace(id="g1")
    return G._image_response(gen, _img(), {}, lambda _l: None, lambda _l: None, lambda *_a: dbg)


def test_image_response_surfaces_low_fidelity():
    r = _resp({"postgen_status": "LOW_FIDELITY", "geometry_status": "UNVERIFIED",
               "geometry_faithful": None})
    assert r.postgen_status == "LOW_FIDELITY"
    # independence: LOW_FIDELITY must not change / imply the geometry status
    assert r.geometry_status == "UNVERIFIED"
    assert r.geometry_faithful is None          # never FAITHFUL


def test_image_response_normal_output_not_low_fidelity():
    r = _resp({"postgen_status": "OK", "geometry_status": "UNVERIFIED"})
    assert r.postgen_status == "OK"             # ordinary output: no warning


def test_image_response_missing_postgen_is_none_backward_compatible():
    # Legacy / older render_debug.json without the field -> None, never a crash.
    r = _resp({"geometry_status": "UNVERIFIED"})
    assert r.postgen_status is None
    assert r.geometry_status == "UNVERIFIED"


def test_save_debug_artifacts_persists_postgen_status(tmp_path, monkeypatch):
    # Written from the runtime result into the authoritative render_debug.json record
    # (not the separate furniture_manifest.json), alongside geometry_status.
    monkeypatch.setattr(G, "DEBUG_ARTIFACTS_DIR", tmp_path)
    G._save_debug_artifacts(
        "g1", 0, "Kitchen", "prompt", "fal", "m", 1216, 832, "success",
        geometry_status="UNVERIFIED", postgen_status="LOW_FIDELITY",
        postgen_reason="output nearly identical to the control base render",
    )
    p = tmp_path / "g1" / "room_0_Kitchen" / "render_debug.json"
    rd = json.loads(p.read_text(encoding="utf-8"))
    assert rd["postgen_status"] == "LOW_FIDELITY"
    assert "nearly identical" in rd["postgen_reason"]
    assert rd["geometry_status"] == "UNVERIFIED"     # preserved, independent


def test_save_debug_artifacts_without_postgen_defaults_none(tmp_path, monkeypatch):
    # Non-success paths (gate/cache/error) that don't pass postgen -> recorded as None.
    monkeypatch.setattr(G, "DEBUG_ARTIFACTS_DIR", tmp_path)
    G._save_debug_artifacts("g2", 0, "Living Area", "p", "fal", "m", 1216, 832, "failed")
    p = tmp_path / "g2" / "room_0_Living Area" / "render_debug.json"
    rd = json.loads(p.read_text(encoding="utf-8"))
    assert rd["postgen_status"] is None


# ── Step 1H — shared post-gen status helper (used by fresh AND cache-hit paths) ──

def test_compute_postgen_status_near_clone_is_low_fidelity():
    base = _solid_png((120, 120, 120))
    near = _solid_png((121, 121, 121))        # mean_abs_diff ~1 < 4.0
    status, reason = G._compute_postgen_status(near, base, True)
    assert status == "LOW_FIDELITY"
    assert reason and "nearly identical" in reason


def test_compute_postgen_status_changed_image_is_ok():
    base = _solid_png((120, 120, 120))
    changed = _solid_png((230, 230, 230))     # mean_abs_diff large >= 4.0
    assert G._compute_postgen_status(changed, base, True) == ("OK", None)


def test_compute_postgen_status_missing_base_is_unknown():
    # No base -> unknown (None), NEVER guessed as OK/LOW_FIDELITY.
    assert G._compute_postgen_status(_solid_png((1, 2, 3)), None, True) == (None, None)


def test_compute_postgen_status_not_control_is_unknown():
    base = _solid_png((1, 2, 3))
    assert G._compute_postgen_status(base, base, False) == (None, None)


def test_compute_postgen_status_undecodable_is_unknown():
    assert G._compute_postgen_status(b"not-a-png", _solid_png((1, 2, 3)), True) == (None, None)


# ── Step 1H — cache-hit path surfaces the status (mocked cache; no live provider) ──

class _CtrlAdapter(AIProviderAdapter):
    name = "fal"
    model = "m"
    supports_control_image = True

    def generate(self, request):  # never reached on a cache hit
        return [_solid_png((9, 9, 9))]


def _run_cache_hit(tmp_path, monkeypatch, cached_png, base_png, gid):
    monkeypatch.setattr(G, "DEBUG_ARTIFACTS_DIR", tmp_path)
    monkeypatch.setattr(G, "_get_cached_render", lambda _k: cached_png)
    monkeypatch.setattr(G, "_classify_base_gate", lambda *_a, **_k: ("", ""))  # gate passes
    canonical = {"furniture": [
        {"uid": "b", "item_id": "bed", "cx": 1, "cy": 2, "w": 30, "h": 40, "rotation": 0},
    ]}
    with mock.patch.object(G, "AI_DEMO_MODE", False):
        _label, _png, _prov, _model, _seed, cache_hit, _ph, _gh, _sh = G._render_room(
            _CtrlAdapter(), "fal", "Modern", ("Kitchen", "p", 1024, 768),
            ("proj", "fp", canonical, None), generation_id=gid, index=0, seed=1,
            fresh_generation=False, base_render=base_png, scene_geometry_faithful=True,
        )
    assert cache_hit is True
    p = tmp_path / gid / "room_0_Kitchen" / "render_debug.json"
    return json.loads(p.read_text(encoding="utf-8"))


def test_cache_hit_near_clone_exposes_low_fidelity(tmp_path, monkeypatch):
    base = _solid_png((120, 120, 120))
    near = _solid_png((121, 121, 121))
    rd = _run_cache_hit(tmp_path, monkeypatch, near, base, "gC1")
    assert rd["postgen_status"] == "LOW_FIDELITY"
    # geometry status is independent / untouched on a cache hit
    assert rd.get("geometry_status") is None


def test_cache_hit_changed_image_exposes_ok(tmp_path, monkeypatch):
    base = _solid_png((120, 120, 120))
    changed = _solid_png((230, 230, 230))
    rd = _run_cache_hit(tmp_path, monkeypatch, changed, base, "gC2")
    assert rd["postgen_status"] == "OK"
    assert rd.get("geometry_status") is None
