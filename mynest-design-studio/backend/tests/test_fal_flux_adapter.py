"""fal.ai FLUX.1 Kontext [dev] image-editing adapter tests.

fal Kontext accepts an ARBITRARY input image (the deterministic base render) as a
base64 data URI in `image_url` — real hosted image editing, no GPU/NIM. These tests
verify registry wiring, diagnostics capability, key requirement, that the outgoing
request carries `image_url`, that the response image URL is downloaded, honest error
preservation, that hosted NVIDIA arbitrary-image edit is still rejected, and that a
provider failure never yields a fabricated success. All HTTP is mocked.
"""

import base64
from io import BytesIO
from unittest import mock

import httpx
import pytest
from PIL import Image

from app.services import prompt_service
from app.services.ai import registry
from app.services.ai.base import AIProviderError, GenerationRequest
from app.services.ai.fal_flux_adapter import (
    FalFluxAdapter,
    _build_fal_edit_prompt,
    fal_config_summary,
    run_fal_transport_diagnostic,
)

_MOD = "app.services.ai.fal_flux_adapter"

# Supported keys in the EDIT-path request body (verified in `_build_body`). The payload
# must never carry an unsupported provider parameter.
_SUPPORTED_EDIT_BODY_KEYS = {
    "prompt", "image_url", "num_images", "output_format", "seed",
    "guidance_scale", "num_inference_steps",
}


def _bedroom_room_prompt(theme: str | None = None):
    intent = {"style": "Modern Luxury"}
    if theme:
        intent["theme"] = theme
    canonical = {"furniture": [
        {"uid": "b", "item_id": "bed", "cx": 500, "cy": 350, "w": 1800, "h": 2000, "rotation": 0},
        {"uid": "s1", "item_id": "side-table", "cx": 300, "cy": 350, "w": 450, "h": 450, "rotation": 0},
        {"uid": "s2", "item_id": "side-table", "cx": 700, "cy": 350, "w": 450, "h": 450, "rotation": 0},
        {"uid": "w", "item_id": "window", "cx": 500, "cy": 800, "w": 1500, "h": 200, "rotation": 0},
    ]}
    _style, rooms = prompt_service.build_room_prompts(canonical, intent)
    return rooms[0][1]


# ── effective FAL edit prompt: inventory once, preservation + negatives, length ──

def test_fal_edit_prompt_has_single_inventory_preamble_and_negatives():
    eff = _build_fal_edit_prompt(_bedroom_room_prompt())
    assert len(eff) <= 2200
    # the exact inventory appears once, in the single EXACT EXISTING INVENTORY block
    assert eff.count("1x Bed, 2x Side Table, 1x Window") == 1
    assert eff.count("EXACT EXISTING INVENTORY") == 1
    # preservation preamble + overriding negatives both present (not duplicated away)
    assert "AUTHORITATIVE source of truth" in eff
    assert "Do NOT add, remove, move, resize, rotate, duplicate, replace" in eff


def test_fal_edit_prompt_too_long_raises_not_silently_truncated():
    # a tiny budget cannot fit the mandatory geometry/inventory/negative constraints →
    # the adapter REFUSES rather than dropping an authoritative constraint.
    with pytest.raises(AIProviderError) as ei:
        _build_fal_edit_prompt(_bedroom_room_prompt(), max_len=200)
    assert "FAL_PROMPT_TOO_LONG" in str(ei.value)


def test_fal_edit_prompt_theme_replaces_house_style_no_contradiction():
    eff = _build_fal_edit_prompt(_bedroom_room_prompt(theme="moody emerald art-deco"))
    assert "moody emerald art-deco" in eff                      # the request's theme is used
    assert "architectural-digest photography" not in eff        # fixed house style replaced, not both
    assert eff.count("EXACT EXISTING INVENTORY") == 1           # inventory still once, authoritative


# ── edit-path payload carries only supported provider parameters ────────────────

def _data_uri() -> str:
    return "data:image/png;base64," + base64.b64encode(_png()).decode()


def test_fal_edit_body_contains_only_supported_keys_defaults():
    body = _adapter()._build_body(_req(), _data_uri())
    assert set(body) <= _SUPPORTED_EDIT_BODY_KEYS
    assert body["image_url"].startswith("data:image/png;base64,")
    assert body["num_images"] == 1 and body["output_format"] == "png"
    # guidance/steps are unset by default → absent (model defaults), not invented
    assert "guidance_scale" not in body and "num_inference_steps" not in body


def test_fal_edit_body_optional_knobs_only_when_configured():
    with mock.patch(f"{_MOD}.FAL_GUIDANCE_SCALE", 4.5), \
         mock.patch(f"{_MOD}.FAL_NUM_INFERENCE_STEPS", 28):
        body = _adapter()._build_body(_req(), _data_uri())
    assert set(body) <= _SUPPORTED_EDIT_BODY_KEYS
    assert body["guidance_scale"] == 4.5 and body["num_inference_steps"] == 28


def _png(color=(170, 140, 110)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (64, 64), color).save(buf, "PNG")
    return buf.getvalue()


def _resp(status, *, json_body=None, content=None, text="", headers=None):
    r = mock.Mock()
    r.status_code = status
    r.json.return_value = json_body if json_body is not None else {}
    r.content = content if content is not None else b""
    r.text = text
    r.headers = headers or {}
    return r


def _adapter(key="fal-secret-key"):
    with mock.patch(f"{_MOD}.FAL_KEY", key), \
         mock.patch(f"{_MOD}.FAL_API_BASE", "https://fal.run"), \
         mock.patch(f"{_MOD}.FAL_IMAGE_MODEL", "fal-ai/flux-kontext/dev"), \
         mock.patch(f"{_MOD}.FAL_IMAGE_EDIT_SUPPORTED", True), \
         mock.patch(f"{_MOD}.FAL_ARBITRARY_IMAGE_SUPPORTED", True):
        return FalFluxAdapter()


def _req(control=None, prompt="restyle in warm minimalism, keep geometry"):
    return GenerationRequest(prompt=prompt, style=None, count=1, width=1024, height=1024,
                             seed=7, control_image=control)


# ── registry ────────────────────────────────────────────────────────────────

def test_fal_registry():
    assert isinstance(registry.get_adapter("fal"), FalFluxAdapter)
    assert isinstance(registry.get_adapter("fal-flux"), FalFluxAdapter)
    # An explicitly requested nvidia provider is NOT silently converted to fal.
    from app.services.ai.nvidia_flux_adapter import NvidiaFluxAdapter
    assert isinstance(registry.get_adapter("nvidia"), NvidiaFluxAdapter)


# ── diagnostics ───────────────────────────────────────────────────────────────

def test_fal_diagnostics():
    # Edit-mode diagnostics (ControlNet OFF): the summary reports the instruction-edit path.
    with mock.patch(f"{_MOD}.FAL_KEY", "k"), \
         mock.patch(f"{_MOD}.FAL_IMAGE_MODEL", "fal-ai/flux-kontext/dev"), \
         mock.patch(f"{_MOD}.FAL_USE_CONTROLNET", False), \
         mock.patch(f"{_MOD}.FAL_IMAGE_EDIT_SUPPORTED", True), \
         mock.patch(f"{_MOD}.FAL_ARBITRARY_IMAGE_SUPPORTED", True):
        s = fal_config_summary()
    assert s["provider"] == "fal"
    assert s["model"] == "fal-ai/flux-kontext/dev"
    assert s["image_input_supported"] is True
    assert s["arbitrary_image_requested"] is True
    assert s["conditioning_mode"] == "edit"
    assert s["api_key_present"] is True


def test_fal_diagnostics_controlnet_mode():
    # ControlNet ON (default production): the summary reports the Canny structure-lock path.
    with mock.patch(f"{_MOD}.FAL_KEY", "k"), \
         mock.patch(f"{_MOD}.FAL_USE_CONTROLNET", True), \
         mock.patch(f"{_MOD}.FAL_CONTROL_MODEL", "fal-ai/flux-control-lora-canny"):
        s = fal_config_summary()
    assert s["model"] == "fal-ai/flux-control-lora-canny"
    assert s["controlnet_enabled"] is True
    assert s["conditioning_mode"] == "canny_controlnet"


# ── key requirement ───────────────────────────────────────────────────────────

def test_fal_requires_key():
    a = _adapter(key="")
    with mock.patch.object(httpx.Client, "post") as post:
        with pytest.raises(AIProviderError) as ei:
            a.generate(_req(control=_png()))
    assert ei.value.status_code == 401
    post.assert_not_called()


# ── image-edit request carries image_url; key is safe ─────────────────────────

def test_fal_image_edit_request_contains_image_url():
    # Edit path (ControlNet OFF): the base render is sent as `image_url` to flux-kontext.
    a = _adapter(key="fal-SUPER-SECRET")
    captured = {}

    def _post(url, json=None, headers=None):  # noqa: A002
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _resp(200, json_body={"images": [{"url": "data:image/png;base64," + base64.b64encode(_png()).decode()}]})

    with mock.patch(f"{_MOD}.FAL_USE_CONTROLNET", False), \
         mock.patch.object(httpx.Client, "post", side_effect=_post):
        out = a.generate(_req(control=_png()))
    assert Image.open(BytesIO(out[0])).format == "PNG"
    body = captured["json"]
    assert body["image_url"].startswith("data:image/png;base64,")  # base render IS the input
    assert captured["url"] == "https://fal.run/fal-ai/flux-kontext/dev"
    assert captured["headers"]["Authorization"] == "Key fal-SUPER-SECRET"
    assert "fal-SUPER-SECRET" not in captured["url"] and "fal-SUPER-SECRET" not in str(body)


def test_fal_controlnet_request_contains_control_image_url():
    # Default path (ControlNet ON): the base render is sent as `control_lora_image_url`
    # to the Canny structure-lock model via the queue gateway; the key stays safe.
    a = _adapter(key="fal-SUPER-SECRET")
    captured = {}

    def _post(url, json=None, headers=None):  # noqa: A002
        captured["url"] = url
        captured["json"] = json
        return _resp(200, json_body={"images": [{"url": "data:image/png;base64," + base64.b64encode(_png()).decode()}]})

    with mock.patch(f"{_MOD}.FAL_USE_CONTROLNET", True), \
         mock.patch.object(httpx.Client, "post", side_effect=_post):
        out = a.generate(_req(control=_png()))
    assert Image.open(BytesIO(out[0])).format == "PNG"
    body = captured["json"]
    assert body["control_lora_image_url"].startswith("data:image/png;base64,")
    assert "flux-control-lora-canny" in captured["url"]
    assert "fal-SUPER-SECRET" not in str(body)


def test_fal_text_to_image_when_no_source_image():
    a = _adapter()
    captured = {}

    def _post(url, json=None, headers=None):  # noqa: A002
        captured["json"] = json
        return _resp(200, json_body={"images": [{"url": "data:image/png;base64," + base64.b64encode(_png()).decode()}]})

    with mock.patch.object(httpx.Client, "post", side_effect=_post):
        a.generate(_req(control=None))
    assert "image_url" not in captured["json"]  # no source image → text-to-image


# ── structural-conditioning experiment (opt-in Canny) regression ───────────────

def test_controlnet_request_locks_image_size_and_init_to_base():
    """Request construction (ControlNet ON): the base is the control map AND the init
    image (same data URI), and image_size is locked to the base dims so the output stays
    pixel-aligned with the deterministic base/camera."""
    a = _adapter(key="k")
    cap = {}

    def _post(url, json=None, headers=None):  # noqa: A002
        cap["url"] = url
        cap["json"] = json
        return _resp(200, json_body={"images": [{"url": "data:image/png;base64," + base64.b64encode(_png()).decode()}]})

    with mock.patch(f"{_MOD}.FAL_USE_CONTROLNET", True), \
         mock.patch(f"{_MOD}.FAL_CONTROL_USE_INIT", True), \
         mock.patch.object(httpx.Client, "post", side_effect=_post):
        a.generate(_req(control=_png()))  # _png() is 64x64
    b = cap["json"]
    assert "flux-control-lora-canny" in cap["url"]
    assert b["control_lora_image_url"].startswith("data:image/png;base64,")
    assert b["image_url"] == b["control_lora_image_url"]      # same base as init (no 2nd source)
    assert b["image_size"] == {"width": 64, "height": 64}     # locked to base dims (alignment)
    assert "control_lora_strength" in b


def test_controlnet_on_without_control_image_does_not_use_control_path():
    """Invalid/missing conditioning input: ControlNet ON but no control image must NOT
    route to the control-lora model (conditioning requires the deterministic base)."""
    a = _adapter(key="k")
    cap = {}

    def _post(url, json=None, headers=None):  # noqa: A002
        cap["url"] = url
        cap["json"] = json
        return _resp(200, json_body={"images": [{"url": "data:image/png;base64," + base64.b64encode(_png()).decode()}]})

    with mock.patch(f"{_MOD}.FAL_USE_CONTROLNET", True), \
         mock.patch.object(httpx.Client, "post", side_effect=_post):
        a.generate(_req(control=None))
    assert "flux-control-lora-canny" not in cap["url"]        # fell back to edit/text path
    assert "control_lora_image_url" not in cap["json"]


@pytest.mark.parametrize("status", [402, 422, 500])
def test_controlnet_provider_failure_raises_no_success(status):
    """Provider failure on the ControlNet path surfaces an honest AIProviderError and
    never fabricates a success image."""
    a = _adapter(key="k")
    with mock.patch(f"{_MOD}.FAL_USE_CONTROLNET", True), \
         mock.patch.object(httpx.Client, "post", return_value=_resp(status, text="boom")):
        with pytest.raises(AIProviderError):
            a.generate(_req(control=_png()))


def test_fal_single_attempt_makes_exactly_one_submission():
    """Cost guard: FAL_SINGLE_ATTEMPT=true submits EXACTLY ONCE on a retryable (500)
    error — no automatic re-POST that could incur a second charge."""
    a = _adapter(key="k")
    calls = {"n": 0}

    def _post(url, json=None, headers=None):  # noqa: A002
        calls["n"] += 1
        return _resp(500, text="boom")

    with mock.patch(f"{_MOD}.FAL_SINGLE_ATTEMPT", True), \
         mock.patch(f"{_MOD}.time.sleep", lambda *a, **k: None), \
         mock.patch.object(httpx.Client, "post", side_effect=_post):
        with pytest.raises(AIProviderError):
            a.generate(_req(control=_png()))
    assert calls["n"] == 1  # exactly one billed submission, no charge-incurring retry


def test_fal_default_retry_budget_preserved_for_other_requests():
    """Default (FAL_SINGLE_ATTEMPT off): the normal bounded retry is unchanged, so this
    guard only affects the opt-in experiment, never other requests."""
    a = _adapter(key="k")
    calls = {"n": 0}

    def _post(url, json=None, headers=None):  # noqa: A002
        calls["n"] += 1
        return _resp(500, text="boom")

    with mock.patch(f"{_MOD}.FAL_SINGLE_ATTEMPT", False), \
         mock.patch(f"{_MOD}.time.sleep", lambda *a, **k: None), \
         mock.patch.object(httpx.Client, "post", side_effect=_post):
        with pytest.raises(AIProviderError):
            a.generate(_req(control=_png()))
    assert calls["n"] >= 2  # bounded retry preserved


# ── response image URL is downloaded ───────────────────────────────────────────

def test_fal_response_image_url_is_downloaded():
    a = _adapter()
    with mock.patch.object(httpx.Client, "post",
                           return_value=_resp(200, json_body={"images": [{"url": "https://fal.media/out.png"}]})), \
         mock.patch.object(httpx.Client, "get",
                           return_value=_resp(200, content=_png(), headers={"content-type": "image/png"})):
        out = a.generate(_req(control=_png()))
    assert Image.open(BytesIO(out[0])).format == "PNG"


# ── provider error is preserved; no fabricated success ─────────────────────────

@pytest.mark.parametrize("status", [401, 402, 403, 422, 500])
def test_fal_provider_error_is_preserved(status):
    a = _adapter(key="fal-TOP-SECRET")
    with mock.patch.object(httpx.Client, "post", return_value=_resp(status, text="err")), \
         mock.patch(f"{_MOD}.time.sleep"):
        with pytest.raises(AIProviderError) as ei:
            a.generate(_req(control=_png()))
    assert ei.value.status_code == status
    assert "fal-TOP-SECRET" not in str(ei.value)   # key never leaked


def test_no_fake_success_on_provider_failure():
    a = _adapter()
    with mock.patch.object(httpx.Client, "post",
                           return_value=_resp(200, json_body={"images": []})):
        with pytest.raises(AIProviderError) as ei:  # 200 but no image is NOT a success
            a.generate(_req(control=_png()))
    assert ei.value.status_code == 502


def test_fal_balance_lock_is_surfaced():
    a = _adapter()
    with mock.patch.object(httpx.Client, "post",
                           return_value=_resp(403, text='{"detail":"User is locked. Reason: TOP_UP."}')):
        with pytest.raises(AIProviderError) as ei:
            a.generate(_req(control=_png()))
    assert ei.value.status_code == 403
    assert "funded" in str(ei.value).lower() or "active" in str(ei.value).lower()


# ── hosted NVIDIA arbitrary-image edit is STILL rejected (unchanged) ───────────

def test_nvidia_hosted_image_edit_still_rejected():
    from app.services.ai import nvidia_flux_adapter as nfa
    with mock.patch.object(nfa, "NVIDIA_API_KEY", "nvapi-x"), \
         mock.patch.object(nfa, "NVIDIA_API_BASE", "https://ai.api.nvidia.com/v1/genai"), \
         mock.patch.object(nfa, "NVIDIA_IMAGE_MODEL", "black-forest-labs/flux.1-kontext-dev"), \
         mock.patch.object(nfa, "NVIDIA_SUPPORTS_IMG2IMG", True), \
         mock.patch.object(nfa, "NVIDIA_ARBITRARY_IMAGE_SUPPORTED", True):
        a = nfa.NvidiaFluxAdapter()
        with mock.patch.object(httpx.Client, "post") as post:
            with pytest.raises(AIProviderError) as ei:
                a.generate(_req(control=_png()))
    assert ei.value.status_code == 422
    assert "NVIDIA_HOSTED_IMAGE_INPUT_UNSUPPORTED" in str(ei.value)
    post.assert_not_called()  # never sends a doomed arbitrary-image request


# ── validate_provider("fal") ───────────────────────────────────────────────────

def test_fal_validation_ready():
    with mock.patch("app.services.ai.registry.FAL_KEY", "k"), \
         mock.patch("app.services.ai.registry.FAL_IMAGE_MODEL", "fal-ai/flux-kontext/dev"):
        res = registry.validate_provider("fal")
    assert res == {
        "provider": "fal", "status": "READY", "model": "fal-ai/flux-kontext/dev",
        "message": "fal.ai FLUX Kontext image editing configured",
    }


def test_fal_validation_not_configured_when_key_missing():
    with mock.patch("app.services.ai.registry.FAL_KEY", ""):
        res = registry.validate_provider("fal")
    assert res["provider"] == "fal" and res["status"] == "NOT_CONFIGURED"


# ── queue (submit -> status -> result) ─────────────────────────────────────────

def test_fal_queue_request_id_response_is_polled():
    a = _adapter()
    data_uri = "data:image/png;base64," + base64.b64encode(_png()).decode()

    def _post(url, json=None, headers=None):  # noqa: A002
        # fal returns a QUEUE response (no images) instead of the completed result.
        return _resp(200, json_body={"request_id": "req-1",
                                     "status_url": "https://queue.fal.run/s",
                                     "response_url": "https://queue.fal.run/r"})

    gets = [
        _resp(200, json_body={"status": "COMPLETED"}),          # status poll
        _resp(200, json_body={"images": [{"url": data_uri}]}),  # result fetch
    ]

    with mock.patch.object(httpx.Client, "post", side_effect=_post), \
         mock.patch.object(httpx.Client, "get", side_effect=gets), \
         mock.patch(f"{_MOD}.time.sleep"):
        out = a.generate(_req(control=_png()))
    assert Image.open(BytesIO(out[0])).format == "PNG"


# ── download validation (never save HTML/JSON as PNG) ──────────────────────────

def test_fal_non_image_content_type_is_rejected():
    a = _adapter()
    with mock.patch.object(httpx.Client, "post",
                           return_value=_resp(200, json_body={"images": [{"url": "https://fal.media/x"}]})), \
         mock.patch.object(httpx.Client, "get",
                           return_value=_resp(200, content=b"<html>error</html>",
                                              headers={"content-type": "text/html"})):
        with pytest.raises(AIProviderError) as ei:
            a.generate(_req(control=_png()))
    assert ei.value.status_code == 502
    assert "non-image content-type" in str(ei.value)


def test_fal_invalid_image_bytes_is_rejected():
    a = _adapter()
    with mock.patch.object(httpx.Client, "post",
                           return_value=_resp(200, json_body={"images": [{"url": "https://fal.media/x"}]})), \
         mock.patch.object(httpx.Client, "get",
                           return_value=_resp(200, content=b"not-an-image",
                                              headers={"content-type": "image/png"})):
        with pytest.raises(AIProviderError) as ei:
            a.generate(_req(control=_png()))
    assert ei.value.status_code == 502
    assert "invalid image payload" in str(ei.value)


def test_fal_server_disconnected_is_structured_connection_error():
    # "Server disconnected without sending a response" == httpx.RemoteProtocolError.
    # It must surface as a CLEAR FAL_CONNECTION_ERROR, not a generic message.
    a = _adapter()
    calls = {"n": 0}

    def _post(url, json=None, headers=None):  # noqa: A002
        calls["n"] += 1
        raise httpx.RemoteProtocolError("Server disconnected without sending a response.")

    with mock.patch.object(httpx.Client, "post", side_effect=_post), \
         mock.patch(f"{_MOD}.time.sleep"):
        with pytest.raises(AIProviderError) as ei:
            a.generate(_req(control=_png()))
    assert ei.value.status_code == 502
    assert "FAL_CONNECTION_ERROR" in str(ei.value)
    assert "RemoteProtocolError" in str(ei.value)
    assert "did not return" not in str(ei.value).lower()   # never the generic message
    # Bounded retry: never an infinite loop.
    assert 1 < calls["n"] <= 3


def test_fal_transient_disconnect_then_success_is_retried():
    a = _adapter()
    calls = {"n": 0}
    ok = _resp(200, json_body={"images": [{"url": "data:image/png;base64," + base64.b64encode(_png()).decode()}]})

    def _post(url, json=None, headers=None):  # noqa: A002
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.RemoteProtocolError("Server disconnected")
        return ok

    with mock.patch.object(httpx.Client, "post", side_effect=_post), \
         mock.patch(f"{_MOD}.time.sleep"):
        out = a.generate(_req(control=_png()))
    assert Image.open(BytesIO(out[0])).format == "PNG"
    assert calls["n"] == 2  # retried once, then succeeded


def test_run_fal_transport_diagnostic_classifies_403_and_hides_secrets():
    with mock.patch(f"{_MOD}.FAL_KEY", "fal-DIAG-SECRET"), \
         mock.patch(f"{_MOD}.FAL_API_BASE", "https://fal.run"), \
         mock.patch(f"{_MOD}.FAL_IMAGE_MODEL", "fal-ai/flux-kontext/dev"), \
         mock.patch.object(httpx.Client, "post",
                           return_value=_resp(403, text='{"detail":"User is locked. Reason: TOP_UP."}',
                                              headers={"x-fal-request-id": "req-diag"})):
        rep = run_fal_transport_diagnostic([("64x64", _png()), ("living", _png((1, 2, 3)))], attempts=2)
    assert rep["case"] == "A_PROVIDER_403"
    assert len(rep["results"]) == 4
    assert all(r["http_status"] == 403 for r in rep["results"])
    assert all(r["request_id"] == "req-diag" for r in rep["results"])
    assert "fal-DIAG-SECRET" not in str(rep)          # key never in the structured result
    assert "base64" not in str(rep).lower() or "base64_length" in str(rep)  # only lengths, not data


def test_run_fal_transport_diagnostic_classifies_transport_failure():
    with mock.patch(f"{_MOD}.FAL_KEY", "k"), \
         mock.patch.object(httpx.Client, "post",
                           side_effect=httpx.RemoteProtocolError("Server disconnected")):
        rep = run_fal_transport_diagnostic([("64x64", _png())], attempts=2)
    assert rep["case"] == "B_TRANSPORT_FAILURE"
    assert all(r["exception_type"] == "RemoteProtocolError" for r in rep["results"])


def test_fal_403_is_provider_error_not_connection_error():
    # A RECEIVED HTTP 403 is a provider response, NEVER a transport/connection error.
    a = _adapter()
    with mock.patch.object(httpx.Client, "post",
                           return_value=_resp(403, text='{"detail":"User is locked. Reason: TOP_UP."}')):
        with pytest.raises(AIProviderError) as ei:
            a.generate(_req(control=_png()))
    assert ei.value.status_code == 403
    assert "TOP_UP" in str(ei.value)
    assert "FAL_CONNECTION_ERROR" not in str(ei.value)   # kept separate from transport drops


def test_fal_403_is_not_retried():
    a = _adapter()
    calls = {"n": 0}

    def _post(url, json=None, headers=None):  # noqa: A002
        calls["n"] += 1
        return _resp(403, text='{"detail":"User is locked. Reason: TOP_UP."}')

    with mock.patch.object(httpx.Client, "post", side_effect=_post), \
         mock.patch(f"{_MOD}.time.sleep"):
        with pytest.raises(AIProviderError) as ei:
            a.generate(_req(control=_png()))
    assert ei.value.status_code == 403
    assert calls["n"] == 1  # billing/auth errors are never retried


def test_fal_empty_images_reports_response_keys():
    a = _adapter()
    with mock.patch.object(httpx.Client, "post",
                           return_value=_resp(200, json_body={"foo": 1, "bar": 2})):
        with pytest.raises(AIProviderError) as ei:
            a.generate(_req(control=_png()))
    assert "no output image" in str(ei.value)
    assert "bar" in str(ei.value) and "foo" in str(ei.value)  # response keys listed
