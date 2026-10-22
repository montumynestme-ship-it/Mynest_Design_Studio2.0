"""Self-hosted NIM routing, model-capability detection, and connection errors.

Covers the fixes for the localhost NIM misconfiguration:
  - deployment_mode / resolve_endpoint: hosted uses {base}/{model}; a self-hosted
    NIM uses {base}/v1/infer (model NOT appended).
  - model capabilities are DATA, not env flags: flux.1-dev is TEXT_TO_IMAGE only;
    an env flag can never fabricate ARBITRARY_IMAGE_INPUT it lacks.
  - the generate() capability gate refuses flux.1-dev + img2img up front with a
    clear NVIDIA_MODEL_CAPABILITY_MISSING error and NO doomed network call.
  - a refused/unreachable endpoint (WinError 10061 -> httpx.ConnectError) surfaces
    a clear NVIDIA_ENDPOINT_UNREACHABLE error, NOT a misleading PROVIDER_TIMEOUT.

All HTTP is mocked; no real network or NIM is required.
"""

from unittest import mock

import httpx
import pytest

from app.services.ai.base import AIProviderError, GenerationRequest
from app.services.ai import nvidia_flux_adapter as nfa
from app.services.ai.nvidia_flux_adapter import (
    ARBITRARY_IMAGE_INPUT,
    IMAGE_EDITING,
    IMAGE_GUIDED_GENERATION,
    NvidiaFluxAdapter,
    TEXT_TO_IMAGE,
    deployment_mode,
    effective_arbitrary_image_input,
    effective_config_summary,
    model_capabilities,
    model_supports_arbitrary_image,
    resolve_endpoint,
)

_MOD = "app.services.ai.nvidia_flux_adapter"
_HOSTED = "https://ai.api.nvidia.com/v1/genai"
_NIM = "http://localhost:8000"
_DEV = "black-forest-labs/flux.1-dev"
_CANNY = "black-forest-labs/flux.1-canny-dev"
_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 400


def _png():
    from io import BytesIO
    from PIL import Image
    buf = BytesIO()
    Image.new("RGB", (32, 32), (120, 120, 120)).save(buf, "PNG")
    return buf.getvalue()


def _req(control=None):
    return GenerationRequest(
        prompt="a room", style=None, count=1, width=1024, height=1024, seed=1,
        control_image=control,
    )


# ── deployment mode + endpoint routing ─────────────────────────────────────────

def test_hosted_mode_and_endpoint():
    assert deployment_mode(_HOSTED) == "hosted"
    assert resolve_endpoint(_HOSTED, _DEV) == f"{_HOSTED}/{_DEV}"


def test_self_hosted_nim_mode_and_infer_route():
    assert deployment_mode(_NIM) == "self_hosted_nim"
    # NIM uses the fixed inference path, model NOT appended.
    assert resolve_endpoint(_NIM, _DEV) == "http://localhost:8000/v1/infer"
    assert _DEV not in resolve_endpoint(_NIM, _DEV)


def test_nim_infer_path_is_configurable():
    with mock.patch(f"{_MOD}.NVIDIA_NIM_INFER_PATH", "/v1/images/generations"):
        assert resolve_endpoint(_NIM, _DEV) == "http://localhost:8000/v1/images/generations"


def test_adapter_endpoint_follows_mode():
    with mock.patch(f"{_MOD}.NVIDIA_API_BASE", _NIM), \
         mock.patch(f"{_MOD}.NVIDIA_API_KEY", "nvapi-x"):
        a = NvidiaFluxAdapter()
    assert a.deployment == "self_hosted_nim"
    assert a._endpoint() == "http://localhost:8000/v1/infer"


# ── model capability model (data, not flags) ───────────────────────────────────

def test_flux_dev_is_text_to_image_only():
    assert model_capabilities(_DEV) == {TEXT_TO_IMAGE}
    assert model_supports_arbitrary_image(_DEV) is False


def test_controlnet_and_edit_models_support_image_input():
    canny = model_capabilities(_CANNY)
    assert IMAGE_GUIDED_GENERATION in canny and ARBITRARY_IMAGE_INPUT in canny
    kontext = model_capabilities("black-forest-labs/flux.1-kontext-dev")
    assert IMAGE_EDITING in kontext and ARBITRARY_IMAGE_INPUT in kontext


def test_unknown_model_is_undetectable():
    assert model_capabilities("my-org/custom-nim") is None
    assert model_supports_arbitrary_image("my-org/custom-nim") is None


def test_effective_capability_flag_cannot_fabricate():
    # flux.1-dev: flag True but model incapable -> effective False.
    assert effective_arbitrary_image_input(_DEV, True) is False
    # canny: flag governs a capable model.
    assert effective_arbitrary_image_input(_CANNY, True) is True
    assert effective_arbitrary_image_input(_CANNY, False) is False
    # unknown NIM model: trust the operator flag (can't detect from name).
    assert effective_arbitrary_image_input("my-org/custom-nim", True) is True


# ── capability gate in generate() ──────────────────────────────────────────────

def test_flux_dev_img2img_refused_with_capability_error_no_request():
    with mock.patch(f"{_MOD}.NVIDIA_API_KEY", "nvapi-secret"), \
         mock.patch(f"{_MOD}.NVIDIA_SUPPORTS_IMG2IMG", True), \
         mock.patch(f"{_MOD}.NVIDIA_IMAGE_MODEL", _DEV):
        a = NvidiaFluxAdapter()
    with mock.patch(f"{_MOD}.NVIDIA_ARBITRARY_IMAGE_SUPPORTED", True), \
         mock.patch.object(httpx.Client, "post") as post:
        with pytest.raises(AIProviderError) as ei:
            a.generate(_req(control=_png()))
    assert ei.value.status_code == 422
    assert "NVIDIA_MODEL_CAPABILITY_MISSING" in str(ei.value)
    assert "flux.1-canny-dev" in str(ei.value)  # names a capable model
    post.assert_not_called()  # never fires a doomed request


def test_capable_model_posts_image_to_nim_infer_route():
    with mock.patch(f"{_MOD}.NVIDIA_API_KEY", "nvapi-secret"), \
         mock.patch(f"{_MOD}.NVIDIA_API_BASE", _NIM), \
         mock.patch(f"{_MOD}.NVIDIA_SUPPORTS_IMG2IMG", True), \
         mock.patch(f"{_MOD}.NVIDIA_IMAGE_MODEL", _CANNY):
        a = NvidiaFluxAdapter()
    captured = {}

    def _post(url, json=None, headers=None):  # noqa: A002
        captured["url"] = url
        captured["json"] = json
        r = mock.Mock()
        r.status_code = 200
        r.text = ""
        r.headers = {}
        r.json.return_value = {"artifacts": [{"base64": _b64(_png())}]}
        return r

    with mock.patch(f"{_MOD}.NVIDIA_ARBITRARY_IMAGE_SUPPORTED", True), \
         mock.patch.object(httpx.Client, "post", side_effect=_post):
        a.generate(_req(control=_png()))
    assert captured["url"] == "http://localhost:8000/v1/infer"
    assert "image" in captured["json"] and captured["json"]["mode"] == "canny"


# ── image-editing (flux.1-kontext-dev, conditioning="edit") on a self-hosted NIM ─

def test_kontext_edit_mode_sends_image_edit_body_on_self_hosted_nim():
    # Arbitrary image editing needs a self-hosted NIM; the hosted API is
    # example_id-only (see the hosted-refusal test below).
    with mock.patch(f"{_MOD}.NVIDIA_API_KEY", "nvapi-secret"), \
         mock.patch(f"{_MOD}.NVIDIA_API_BASE", _NIM), \
         mock.patch(f"{_MOD}.NVIDIA_SUPPORTS_IMG2IMG", True), \
         mock.patch(f"{_MOD}.NVIDIA_IMG2IMG_MODE", "edit"), \
         mock.patch(f"{_MOD}.NVIDIA_IMAGE_MODEL", "black-forest-labs/flux.1-kontext-dev"):
        a = NvidiaFluxAdapter()
    assert a.deployment == "self_hosted_nim"
    assert a.mode == "edit"
    assert a._endpoint() == "http://localhost:8000/v1/infer"
    captured = {}

    def _post(url, json=None, headers=None):  # noqa: A002
        captured["url"] = url
        captured["json"] = json
        r = mock.Mock()
        r.status_code = 200
        r.text = ""
        r.headers = {}
        r.json.return_value = {"artifacts": [{"base64": _b64(_png())}]}
        return r

    with mock.patch(f"{_MOD}.NVIDIA_ARBITRARY_IMAGE_SUPPORTED", True), \
         mock.patch.object(httpx.Client, "post", side_effect=_post):
        a.generate(_req(control=_png()))
    assert captured["url"] == "http://localhost:8000/v1/infer"
    b = captured["json"]
    assert b["image"].startswith("data:image/png;base64,")  # base render IS the edit input
    # Verified live: kontext REJECTS a `mode` field (422 extra_forbidden), so the
    # edit body must NOT include it.
    assert "mode" not in b
    assert "preprocess_image" not in b  # edit is not canny/depth preprocessing
    assert "width" not in b and "height" not in b  # input image dictates aspect


def test_hosted_arbitrary_image_refused_even_for_capable_model_no_request():
    # VERIFIED LIVE: the hosted endpoint accepts only example_id images and rejects
    # an arbitrary base64/asset image (422). Even kontext (an image-EDIT model) can't
    # take the base render on hosted — refuse up front, send nothing.
    with mock.patch(f"{_MOD}.NVIDIA_API_KEY", "nvapi-secret"), \
         mock.patch(f"{_MOD}.NVIDIA_API_BASE", "https://ai.api.nvidia.com/v1/genai"), \
         mock.patch(f"{_MOD}.NVIDIA_SUPPORTS_IMG2IMG", True), \
         mock.patch(f"{_MOD}.NVIDIA_IMG2IMG_MODE", "edit"), \
         mock.patch(f"{_MOD}.NVIDIA_IMAGE_MODEL", "black-forest-labs/flux.1-kontext-dev"):
        a = NvidiaFluxAdapter()
    assert a.deployment == "hosted"
    with mock.patch(f"{_MOD}.NVIDIA_ARBITRARY_IMAGE_SUPPORTED", True), \
         mock.patch.object(httpx.Client, "post") as post:
        with pytest.raises(AIProviderError) as ei:
            a.generate(_req(control=_png()))
    assert ei.value.status_code == 422
    assert "NVIDIA_HOSTED_IMAGE_INPUT_UNSUPPORTED" in str(ei.value)
    assert "self-hosted" in str(ei.value).lower()
    post.assert_not_called()


def test_hosted_summary_image_input_false_even_for_kontext():
    with mock.patch(f"{_MOD}.NVIDIA_API_BASE", "https://ai.api.nvidia.com/v1/genai"), \
         mock.patch(f"{_MOD}.NVIDIA_IMAGE_MODEL", "black-forest-labs/flux.1-kontext-dev"), \
         mock.patch(f"{_MOD}.NVIDIA_SUPPORTS_IMG2IMG", True), \
         mock.patch(f"{_MOD}.NVIDIA_ARBITRARY_IMAGE_SUPPORTED", True):
        s = effective_config_summary()
    assert s["deployment_mode"] == "hosted"
    assert s["image_input_supported"] is False          # hosted is example_id-only
    assert IMAGE_EDITING in s["model_declared_capabilities"]  # model CAN; deployment can't


# ── connection refused / unreachable ───────────────────────────────────────────

def test_connect_error_is_endpoint_unreachable_not_timeout():
    with mock.patch(f"{_MOD}.NVIDIA_API_KEY", "nvapi-secret"), \
         mock.patch(f"{_MOD}.NVIDIA_API_BASE", _NIM):
        a = NvidiaFluxAdapter()  # text-to-image; makes a network call
    calls = {"n": 0}

    def _post(url, json=None, headers=None):  # noqa: A002
        calls["n"] += 1
        raise httpx.ConnectError("[WinError 10061] actively refused")

    with mock.patch.object(httpx.Client, "post", side_effect=_post), \
         mock.patch(f"{_MOD}.time.sleep"):
        with pytest.raises(AIProviderError) as ei:
            a.generate(_req())
    assert ei.value.status_code == 503
    msg = str(ei.value)
    assert "NVIDIA_ENDPOINT_UNREACHABLE" in msg
    assert "PROVIDER_TIMEOUT" not in msg
    assert "http://localhost:8000/v1/infer" in msg
    assert calls["n"] == 1  # fails fast, no retry storm on a refused connection


# ── effective config summary (diagnostics single source of truth) ──────────────

def test_effective_summary_does_not_overclaim_for_flux_dev():
    with mock.patch(f"{_MOD}.NVIDIA_API_BASE", _NIM), \
         mock.patch(f"{_MOD}.NVIDIA_IMAGE_MODEL", _DEV), \
         mock.patch(f"{_MOD}.NVIDIA_SUPPORTS_IMG2IMG", True), \
         mock.patch(f"{_MOD}.NVIDIA_ARBITRARY_IMAGE_SUPPORTED", True):
        s = effective_config_summary()
    assert s["deployment_mode"] == "self_hosted_nim"
    assert s["endpoint"] == "http://localhost:8000/v1/infer"
    assert s["arbitrary_image_requested"] is True
    assert s["image_input_supported"] is False  # flux.1-dev cannot, despite the flag
    assert s["model_declared_capabilities"] == [TEXT_TO_IMAGE]


def test_effective_summary_reports_capable_model():
    with mock.patch(f"{_MOD}.NVIDIA_API_BASE", _NIM), \
         mock.patch(f"{_MOD}.NVIDIA_IMAGE_MODEL", _CANNY), \
         mock.patch(f"{_MOD}.NVIDIA_ARBITRARY_IMAGE_SUPPORTED", True):
        s = effective_config_summary()
    assert s["image_input_supported"] is True
    assert ARBITRARY_IMAGE_INPUT in s["model_declared_capabilities"]


def _b64(data: bytes) -> str:
    import base64
    return base64.b64encode(data).decode("ascii")
