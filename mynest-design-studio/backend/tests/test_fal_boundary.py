"""fal.ai generation-boundary contract.

ONLY a validated deterministic base render + validated design version + room identity
+ an AI styling prompt may reach fal. fal must NEVER receive the original PDF, an
editor screenshot, an unvalidated/stale Three.js base, a mock/fallback image, or
independently-generated furniture. The AI prompt must explicitly preserve geometry /
walls / doors / windows / furniture identity-count-position-rotation-dimensions /
room assignment / camera composition, and may only change materials/lighting/appearance.

Every test here is OFFLINE: the fal adapter's `httpx.Client` is replaced so a real
network request fails the test loudly. A gated (invalid) base must never even reach
the network; the happy path exercises the real request-building code against a fake
HTTP client (still no real fal call).
"""

import base64
from contextlib import contextmanager
from io import BytesIO
from unittest import mock

import pytest
from PIL import Image, ImageDraw

from app.services import base_render_service as brs
from app.services import generation_service
from app.services.ai import fal_flux_adapter
from app.services.ai.base import GenerationRequest
from app.services.ai.fal_flux_adapter import FalFluxAdapter
from app.services.floor_plan_service import FloorPlanError

CANONICAL = {"furniture": [
    {"uid": "b-1", "item_id": "bed", "cx": 500, "cy": 350, "w": 1800, "h": 2000, "rotation": 0},
]}


def _png(w=64, h=64, c=(30, 40, 60), c2=(210, 190, 150)) -> bytes:
    """A deterministic NON-blank png (two-tone), distinct per color pair."""
    img = Image.new("RGB", (w, h), c)
    ImageDraw.Draw(img).rectangle([0, 0, w, h // 2], fill=c2)
    buf = BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _blank_png(w=64, h=64) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (w, h), (0, 0, 0)).save(buf, "PNG")
    return buf.getvalue()


@contextmanager
def _no_network():
    """Guarantee NO fal network call: any httpx.Client use inside the fal adapter
    raises. A correctly-gated invalid base never reaches this."""
    boom = mock.MagicMock(side_effect=AssertionError("fal network call attempted"))
    with mock.patch.object(fal_flux_adapter.httpx, "Client", boom):
        yield boom


def _render(adapter, base_render, *, faithful=True):
    return generation_service._render_room(
        adapter, "fal", "Modern", ("Bedroom 1", "p", 1024, 768),
        ("proj", "fp", CANONICAL, None),
        generation_id="g", index=0, seed=1, fresh_generation=True,
        base_render=base_render, scene_geometry_faithful=faithful,
    )


# ── PROMPT CONTRACT: preserves geometry, allows only styling ────────────────────
def test_prompt_explicitly_preserves_geometry_and_allows_only_styling():
    adapter = FalFluxAdapter()
    body = adapter._build_body(
        GenerationRequest(prompt="Scandinavian warm palette", style="Modern", count=1, seed=7),
        image_data_uri="data:image/png;base64,QUJD",
    )
    p = body["prompt"].lower()
    # Explicitly preserved attributes (task list).
    for token in ("geometr", "wall", "door", "window", "camera",
                  "position", "rotation", "dimension", "count", "room"):
        assert token in p, f"prompt must preserve '{token}'"
    assert "identity" in p
    # Only-styling allowances.
    for token in ("material", "texture", "color", "lighting"):
        assert token in p, f"prompt must allow restyling '{token}'"
    # Must forbid moving/adding/removing objects, and declare the image authoritative.
    assert "do not move" in p or "do not add" in p or "do not" in p
    assert "source of truth" in p or "authoritative" in p


def test_only_image_prompt_and_render_params_reach_fal():
    adapter = FalFluxAdapter()
    body = adapter._build_body(
        GenerationRequest(prompt="x", style="Modern", count=1, seed=3),
        image_data_uri="data:image/png;base64,QUJD",
    )
    # Exactly the allowed payload — never a PDF, file upload, screenshot, or scene JSON.
    assert set(body.keys()) <= {"prompt", "image_url", "num_images", "output_format", "seed"}
    assert body["image_url"].startswith("data:image/")
    for forbidden in ("pdf", "file", "document", "scene", "canonical", "furniture"):
        assert forbidden not in body


# ── INVALID BASE CANNOT REACH FAL (no network) ──────────────────────────────────
def test_missing_base_gated_before_fal():
    with _no_network() as boom:
        with pytest.raises(FloorPlanError) as ei:
            _render(FalFluxAdapter(), None)
    assert "BASE_RENDER_MISSING" in str(ei.value.detail)
    boom.assert_not_called()  # fal was never contacted


def test_blank_base_gated_before_fal():
    with _no_network() as boom:
        with pytest.raises(FloorPlanError) as ei:
            _render(FalFluxAdapter(), _blank_png())
    assert "BASE_RENDER_BLANK" in str(ei.value.detail)
    boom.assert_not_called()


def test_corrupt_base_gated_before_fal():
    with _no_network() as boom:
        with pytest.raises(FloorPlanError) as ei:
            _render(FalFluxAdapter(), b"\x00 not a png \xff")
    assert "BASE_RENDER_CORRUPT" in str(ei.value.detail)
    boom.assert_not_called()


def test_geometry_invalid_scene_gated_before_fal():
    with _no_network() as boom:
        with pytest.raises(FloorPlanError) as ei:
            _render(FalFluxAdapter(), _png(), faithful=False)
    assert "BASE_GEOMETRY_INVALID" in str(ei.value.detail)
    boom.assert_not_called()


# ── Stale design version / wrong room are rejected (base-render contract) ────────
def test_base_contract_rejects_stale_version_wrong_room_and_wrong_size():
    good = _png(1216, 832)
    # stale design version
    v = brs.validate_base_render(good, expected_version_id="v2", declared_version_id="v1",
                                 expected_width=1216, expected_height=832)
    assert v["code"] == brs.WRONG_VERSION
    # wrong room
    v = brs.validate_base_render(good, expected_room_key="living-area",
                                 declared_room_key="kitchen",
                                 expected_width=1216, expected_height=832)
    assert v["code"] == brs.WRONG_ROOM
    # wrong size (e.g. an editor-UI screenshot at the wrong resolution)
    v = brs.validate_base_render(_png(800, 600), expected_width=1216, expected_height=832)
    assert v["code"] == brs.WRONG_SIZE
    # a valid, current, right-room, right-size capture passes
    v = brs.validate_base_render(good, expected_version_id="v2", declared_version_id="v2",
                                 expected_room_key="living-area", declared_room_key="living-area",
                                 expected_width=1216, expected_height=832)
    assert v["ok"] is True and v["code"] is None


# ── VALID BASE reaches the real fal request builder (fake HTTP, no real network) ─
def test_valid_base_reaches_fal_request_with_only_validated_inputs():
    captured: dict = {}
    out_img = _png(64, 64, c=(90, 160, 110), c2=(240, 230, 210))  # distinct from base
    out_uri = "data:image/png;base64," + base64.b64encode(out_img).decode()

    class _Resp:
        status_code = 200
        headers = {"x-fal-request-id": "req-test"}
        text = '{"images":[{"url":"..."}]}'

        def json(self):
            return {"images": [{"url": out_uri, "width": 64, "height": 64}]}

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, endpoint, json=None, headers=None):
            captured["endpoint"] = endpoint
            captured["body"] = json
            captured["auth"] = (headers or {}).get("Authorization")
            return _Resp()

    base = _png(64, 64)  # a VALID non-blank base render
    adapter = FalFluxAdapter()
    adapter.api_key = "test-key"                 # avoid the 401 config guard
    adapter.arbitrary_image_effective = True     # genuine edit capability

    with mock.patch.object(fal_flux_adapter.httpx, "Client", _FakeClient), \
         mock.patch("app.services.generation_service.AI_DEMO_MODE", False):
        label, png, provider_used, model, *_ = _render(adapter, base)

    # The provider WAS reached with exactly the validated inputs. The production path is the
    # verified instruction-EDIT model (fal-ai/flux-kontext/dev): the deterministic base render
    # is sent as `image_url` (image-to-image), carried pixel-identical, and the body contains
    # ONLY prompt + base image + render params (never a PDF/scene/file). ControlNet is OPT-IN.
    assert "fal-ai/flux-kontext/dev" in captured["endpoint"]
    assert "control_lora_image_url" not in captured["body"]       # not the ControlNet path
    assert captured["body"]["image_url"].startswith("data:image/png;base64,")
    sent = base64.b64decode(captured["body"]["image_url"].split(",", 1)[1])
    assert Image.open(BytesIO(sent)).size == (64, 64)   # the base render, re-encoded
    assert "authoritative" in captured["body"]["prompt"].lower()  # preservation preamble present
    assert set(captured["body"].keys()) <= {
        "prompt", "image_url", "num_images", "output_format", "seed",
        "guidance_scale", "num_inference_steps"}
    for forbidden in ("pdf", "file", "document", "scene", "canonical", "furniture"):
        assert forbidden not in captured["body"]
    assert captured["auth"].startswith("Key ")          # server-side key, not in payload
    assert label == "Bedroom 1" and png  # a real image came back through the boundary


# ── STEP 5: adapter transmits the control image PIXEL-IDENTICAL (B integrity) ─────
def test_adapter_transmits_control_image_pixel_identical():
    """The image fal receives must be the SAME image as the (Bedroom 1) base render —
    pixel-identical through the adapter encode (base64 of _to_png is lossless on pixels),
    proving no cross-room / corruption between GenerationRequest and the fal body."""
    from app.services.ai.nvidia_flux_adapter import _to_png
    base = _png(1216, 832, c=(40, 60, 90), c2=(180, 160, 140))  # stand-in bedroom base
    uri = "data:image/png;base64," + base64.b64encode(_to_png(base)).decode()
    adapter = FalFluxAdapter()
    body = adapter._build_body(
        GenerationRequest(prompt="[Bedroom 1] 1x Bed, 1x Wardrobe", style="M", count=1, seed=1), uri)
    assert body["image_url"] == uri
    dec = base64.b64decode(body["image_url"].split(",", 1)[1])
    a = Image.open(BytesIO(base)).convert("RGB")
    b = Image.open(BytesIO(dec)).convert("RGB")
    assert a.size == b.size == (1216, 832)          # dimensions preserved
    assert list(a.getdata()) == list(b.getdata())    # pixel-identical (no mutation)
    # The geometry-preservation preamble is present in the final prompt. (NOTE: STEP 5
    # found that _clean_prompt strips the room-specific positive inventory, so the final
    # prompt is room-agnostic — that is reported as the stage-B divergence, not asserted
    # as correct here.)
    assert "authoritative" in body["prompt"].lower()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 5 FIX — FAL has its OWN prompt builder; room identity + inventory survive and
# lead; NVIDIA's _clean_prompt is NOT used by FAL. These assert the FIXED behavior.
# ═══════════════════════════════════════════════════════════════════════════════
from app.services import floor_plan_service as _fps  # noqa: E402
from app.services import prompt_service as _ps  # noqa: E402
from app.services.ai import fal_flux_adapter as _fal  # noqa: E402
from app.services.ai.fal_flux_adapter import _EDIT_PREAMBLE as _PRE  # noqa: E402
from app.services.ai.fal_flux_adapter import _build_fal_edit_prompt  # noqa: E402

_FID = "f6b65d2b-4f96-4931-9f08-67dbd09776f6"


def _room_prompt(room):
    canon = _fps.get_canonical(_FID)
    return _ps.build_room_prompts(canon, {"style": "Modern Luxury"}, requested_rooms=[room])[1][0][1]


def _fal_final(room):
    return _build_fal_edit_prompt(_room_prompt(room))


# A. NVIDIA cleaner is NOT used by FAL.
def test_step5_fal_does_not_use_nvidia_clean_prompt():
    assert "_clean_prompt" not in dir(_fal)  # import removed from the fal adapter module
    from app.services.ai.nvidia_flux_adapter import _clean_prompt
    rp = _room_prompt("Bedroom 1")
    assert _fal_final("Bedroom 1") != _clean_prompt(_PRE + "\n\n" + rp)


def test_step5_original_room_prompt_contains_inventory():
    rp = _room_prompt("Bedroom 1")
    for token in ("bedroom 1", "1x Bed", "2x Side Table", "1x Wardrobe", "1x Dressing Table"):
        assert token in rp, f"original prompt should contain {token!r}"


# B. Bedroom 1 final FAL prompt contains POSITIVE room identity + inventory.
def test_step5_fal_final_contains_positive_room_identity_and_inventory():
    low = _fal_final("Bedroom 1").lower()
    assert "room:" in low and "bedroom 1" in low
    assert "exact existing inventory" in low
    for token in ("bed", "side table", "wardrobe", "dressing table", "window", "door"):
        assert token in low, f"final FAL prompt must positively contain {token!r}"


# E. Geometry-preservation preamble remains present.
def test_step5_fal_final_keeps_geometry_preamble():
    low = _fal_final("Bedroom 1").lower()
    assert "authoritative" in low and "transform this interior layout" in low


# C + §8 regression: the five rooms' final FAL prompts are NOT identical.
def test_step5_fal_final_prompts_distinct_per_room():
    finals = {r: _fal_final(r) for r in
              ("Bedroom 1", "Bedroom 2", "Bedroom 3", "Living Area", "Kitchen")}
    assert len(set(finals.values())) == 5, \
        "REGRESSION: FAL final prompts must be room-specific, never identical (NVIDIA cleaner reintroduced?)"


# §8 negative regression: Bedroom 1 must carry positive identity/inventory.
def test_step5_regression_bedroom1_requires_positive_identity():
    low = _fal_final("Bedroom 1").lower()
    assert "bedroom 1" in low and "bed" in low and "exact existing inventory" in low, \
        "REGRESSION: Bedroom 1 final prompt lost its positive room identity/inventory"


# D. The HTTP body prompt is exactly the FAL builder output (no second rewrite).
def test_step5_adapter_body_is_fal_builder_output():
    rp = _room_prompt("Bedroom 1")
    body = FalFluxAdapter()._build_body(
        GenerationRequest(prompt=rp, style="Modern Luxury", count=1, seed=1),
        "data:image/png;base64,QUJD")
    assert body["prompt"] == _build_fal_edit_prompt(rp)


# F. No API key appears in prompt logs.
def test_step5_adapter_does_not_log_api_key(caplog):
    import logging
    boom = mock.MagicMock(side_effect=AssertionError("net"))
    ad = FalFluxAdapter()
    ad.api_key = "nvapi-SECRET-DO-NOT-LOG"
    ad.arbitrary_image_effective = True
    with mock.patch.object(_fal.httpx, "Client", boom), caplog.at_level(logging.INFO):
        try:
            ad.generate(GenerationRequest(prompt="x", style="M", count=1, seed=1,
                                          control_image=_png(64, 64), room_label="Bedroom 1"))
        except Exception:
            pass
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "nvapi-SECRET-DO-NOT-LOG" not in text  # API key never logged


# ── Controlled img2img structure-control knobs (isolated, unset-by-default) ────
def test_fal_body_has_no_structure_knobs_when_unset():
    """Default: FAL body carries NO guidance_scale / num_inference_steps (model defaults),
    so enabling them is an explicit, isolated change."""
    with mock.patch.object(fal_flux_adapter, "FAL_GUIDANCE_SCALE", None), \
         mock.patch.object(fal_flux_adapter, "FAL_NUM_INFERENCE_STEPS", None):
        body = FalFluxAdapter()._build_body(
            GenerationRequest(prompt="[Bedroom 1] 1x Bed", style="M", count=1, seed=1),
            "data:image/png;base64,AAAA")
    assert "guidance_scale" not in body and "num_inference_steps" not in body


def test_fal_body_includes_structure_knobs_when_set():
    with mock.patch.object(fal_flux_adapter, "FAL_GUIDANCE_SCALE", 6.5), \
         mock.patch.object(fal_flux_adapter, "FAL_NUM_INFERENCE_STEPS", 40):
        body = FalFluxAdapter()._build_body(
            GenerationRequest(prompt="[Bedroom 1] 1x Bed", style="M", count=1, seed=1),
            "data:image/png;base64,AAAA")
    assert body["guidance_scale"] == 6.5 and body["num_inference_steps"] == 40


# ═══════════════════════════════════════════════════════════════════════════════
# CANNY CONTROL-LoRA — REAL structural conditioning (geometry lock). The deterministic
# base render becomes the CONTROL image; fal extracts its Canny edge map and locks the
# output's structure to it, so furniture/walls/openings cannot drift. One generalized
# path for every room (no per-room branching). Verified against the fal OpenAPI schema
# (fal-ai/flux-control-lora-canny). All OFFLINE — no paid fal call.
# ═══════════════════════════════════════════════════════════════════════════════
def _capture_generate(adapter, request):
    """Drive adapter.generate() against a fake HTTP client; return the captured body
    and endpoint without any real network call."""
    captured: dict = {}
    out_uri = "data:image/png;base64," + base64.b64encode(_png(64, 64, c=(9, 9, 9))).decode()

    class _Resp:
        status_code = 200
        headers = {"x-fal-request-id": "req-cn"}
        text = '{"images":[{"url":"..."}]}'

        def json(self):
            return {"images": [{"url": out_uri, "width": 64, "height": 64}]}

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, endpoint, json=None, headers=None):
            captured["endpoint"] = endpoint
            captured["body"] = json
            return _Resp()

        def get(self, url, headers=None):
            return _Resp()

    adapter.api_key = "test-key"
    adapter.arbitrary_image_effective = True
    with mock.patch.object(fal_flux_adapter.httpx, "Client", _FakeClient):
        out = adapter.generate(request)
    captured["out"] = out
    return captured


def test_controlnet_route_uses_canny_endpoint_and_control_image():
    """With FAL_USE_CONTROLNET on and a base render present, generate() targets the
    Canny Control-LoRA endpoint, sends the base as `control_lora_image_url` (NOT the
    edit `image_url`), and matches image_size to the base dimensions."""
    with mock.patch.object(fal_flux_adapter, "FAL_USE_CONTROLNET", True), \
         mock.patch.object(fal_flux_adapter, "FAL_CONTROL_USE_INIT", False), \
         mock.patch.object(fal_flux_adapter, "FAL_CONTROL_STRENGTH", None):
        cap = _capture_generate(
            FalFluxAdapter(),
            GenerationRequest(prompt="[Bedroom 1] 1x Bed, 1x Wardrobe", style="M", count=1,
                              seed=5, control_image=_png(1216, 832), room_label="Bedroom 1"))
    assert "fal-ai/flux-control-lora-canny" in cap["endpoint"]
    body = cap["body"]
    assert body["control_lora_image_url"].startswith("data:image/png;base64,")
    assert "image_url" not in body                      # init disabled for this case
    assert body["image_size"] == {"width": 1216, "height": 832}
    assert body["control_lora_strength"] == 1.0         # full geometry lock by default
    assert body["output_format"] == "png" and body["seed"] == 5
    # The control image is the base render, pixel-identical through the adapter encode.
    dec = base64.b64decode(body["control_lora_image_url"].split(",", 1)[1])
    assert Image.open(BytesIO(dec)).size == (1216, 832)
    assert cap["out"] and isinstance(cap["out"][0], (bytes, bytearray))


def test_controlnet_strength_is_clamped_to_schema_range():
    with mock.patch.object(fal_flux_adapter, "FAL_USE_CONTROLNET", True), \
         mock.patch.object(fal_flux_adapter, "FAL_CONTROL_STRENGTH", 9.0):  # out of [0,2]
        cap = _capture_generate(
            FalFluxAdapter(),
            GenerationRequest(prompt="[Bedroom 1] 1x Bed", style="M", count=1, seed=1,
                              control_image=_png(1216, 832), room_label="Bedroom 1"))
    assert cap["body"]["control_lora_strength"] == 2.0  # clamped to the schema max


def test_controlnet_init_image_is_the_same_validated_base():
    """When the img2img init is enabled, `image_url` is the SAME base render as
    `control_lora_image_url` — materials seed from the base, geometry from the base.
    No independent/second image is ever introduced."""
    with mock.patch.object(fal_flux_adapter, "FAL_USE_CONTROLNET", True), \
         mock.patch.object(fal_flux_adapter, "FAL_CONTROL_USE_INIT", True):
        cap = _capture_generate(
            FalFluxAdapter(),
            GenerationRequest(prompt="[Bedroom 1] 1x Bed", style="M", count=1, seed=1,
                              control_image=_png(1216, 832), room_label="Bedroom 1"))
    body = cap["body"]
    assert body["image_url"] == body["control_lora_image_url"]  # identical, not a 2nd image


def test_controlnet_disabled_falls_back_to_edit_path():
    """With FAL_USE_CONTROLNET off, the legacy instruction-edit body (image_url) is used
    and the edit endpoint (flux-kontext) is targeted — the switch is a single flag."""
    with mock.patch.object(fal_flux_adapter, "FAL_USE_CONTROLNET", False):
        cap = _capture_generate(
            FalFluxAdapter(),
            GenerationRequest(prompt="[Bedroom 1] 1x Bed", style="M", count=1, seed=1,
                              control_image=_png(1216, 832), room_label="Bedroom 1"))
    assert "flux-control-lora-canny" not in cap["endpoint"]
    assert "image_url" in cap["body"] and "control_lora_image_url" not in cap["body"]


def test_controlnet_prompt_preserves_geometry_and_allows_only_styling():
    """The ControlNet prompt still carries the room identity + inventory and the
    materials-only allowance (structure is additionally locked by the Canny edges)."""
    body = FalFluxAdapter()._build_control_body(
        GenerationRequest(prompt="[Bedroom 1] 1x Bed, 1x Wardrobe", style="M", count=1, seed=1),
        "data:image/png;base64,AAAA", 1216, 832)
    p = body["prompt"].lower()
    for token in ("geometr", "wall", "door", "window", "material", "texture", "color", "lighting"):
        assert token in p
    assert "authoritative" in p
