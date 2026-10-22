"""NVIDIA FLUX.1-dev TEXT-TO-IMAGE (mode="base") render-path regression tests.

Locks the CURRENT contract after the HTTP 502 fix: the hosted flux.1-dev endpoint
is text-to-image only, so the app must send a clean base request (no image /
example_id / ControlNet payload), keep the API key server-side and out of every
log, classify each provider failure honestly, and — because base mode needs no
control image — never raise BASE_GEOMETRY_INVALID for a text-to-image render.

All HTTP is mocked; no real network call is made.
"""

import base64
from io import BytesIO
from unittest import mock

import httpx
import pytest
from PIL import Image

from app.services import floor_plan_service, generation_service
from app.services.ai.base import AIProviderAdapter, AIProviderError, GenerationRequest
from app.services.ai.nvidia_flux_adapter import (
    NvidiaFluxAdapter,
    _safe_body_summary,
)

OFFICIAL_ENDPOINT = (
    "https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.1-dev"
)


def _png_bytes(color=(200, 180, 150)) -> bytes:
    img = Image.new("RGB", (16, 16), color)
    for y in range(8):
        for x in range(16):
            img.putpixel((x, y), (30, 40, 60))
    buf = BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


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
    return {"artifacts": [{"base64": _b64(_png_bytes())}]}


def _adapter(*, key="nvapi-secret") -> NvidiaFluxAdapter:
    # Text-to-image is the default; force it explicitly regardless of local .env.
    with mock.patch("app.services.ai.nvidia_flux_adapter.NVIDIA_API_KEY", key), \
         mock.patch("app.services.ai.nvidia_flux_adapter.NVIDIA_SUPPORTS_IMG2IMG", False):
        return NvidiaFluxAdapter()


def _capture_post(captured):
    def _post(url, json=None, headers=None):  # noqa: A002
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _resp(200, json_body=_artifacts_ok())
    return _post


# ── Endpoint + request contract ──────────────────────────────────────────────

def test_endpoint_is_official_flux_dev():
    with mock.patch("app.services.ai.nvidia_flux_adapter.NVIDIA_API_BASE",
                    "https://ai.api.nvidia.com/v1/genai"), \
         mock.patch("app.services.ai.nvidia_flux_adapter.NVIDIA_IMAGE_MODEL",
                    "black-forest-labs/flux.1-dev"), \
         mock.patch("app.services.ai.nvidia_flux_adapter.NVIDIA_API_KEY", "nvapi-x"):
        a = NvidiaFluxAdapter()
    assert a._endpoint() == OFFICIAL_ENDPOINT


def test_base_mode_body_is_pure_text_to_image_even_with_control_image():
    a = _adapter()
    assert a.mode == "base"
    assert a.supports_control_image is False
    captured: dict = {}
    with mock.patch.object(httpx.Client, "post", side_effect=_capture_post(captured)):
        a.generate(GenerationRequest(
            prompt="a living room", style=None, count=1,
            width=1024, height=768, control_image=_png_bytes(),
        ))
    body = captured["json"]
    assert body["mode"] == "base"                       # explicit base mode
    assert body["width"] == 1024 and body["height"] == 768
    assert {"prompt", "steps", "cfg_scale", "seed"} <= set(body)
    # NONE of the img2img / control payloads may be present.
    for forbidden in ("image", "example_id", "canny", "depth", "preprocess_image",
                      "response_format", "controlnet"):
        assert forbidden not in body, f"base request must not send {forbidden!r}"


def test_posts_to_official_endpoint():
    a = _adapter()
    captured: dict = {}
    with mock.patch("app.services.ai.nvidia_flux_adapter.NVIDIA_API_BASE",
                    "https://ai.api.nvidia.com/v1/genai"), \
         mock.patch("app.services.ai.nvidia_flux_adapter.NVIDIA_IMAGE_MODEL",
                    "black-forest-labs/flux.1-dev"), \
         mock.patch("app.services.ai.nvidia_flux_adapter.NVIDIA_API_KEY", "nvapi-secret"):
        a2 = NvidiaFluxAdapter()
        with mock.patch.object(httpx.Client, "post", side_effect=_capture_post(captured)):
            a2.generate(GenerationRequest(prompt="p", style=None, count=1))
    assert captured["url"] == OFFICIAL_ENDPOINT


# ── API key handling (server-side only, never leaked) ────────────────────────

def test_key_is_server_side_and_never_in_url_or_body():
    a = _adapter(key="nvapi-supersecret")
    captured: dict = {}
    with mock.patch.object(httpx.Client, "post", side_effect=_capture_post(captured)):
        a.generate(GenerationRequest(prompt="p", style=None, count=1))
    assert captured["headers"]["Authorization"] == "Bearer nvapi-supersecret"
    assert "nvapi-supersecret" not in captured["url"]
    assert "nvapi-supersecret" not in str(captured["json"])


def test_missing_key_raises_401_before_any_request():
    a = _adapter(key="")
    with mock.patch.object(httpx.Client, "post") as post:
        with pytest.raises(AIProviderError) as ei:
            a.generate(GenerationRequest(prompt="p", style=None, count=1))
    assert ei.value.status_code == 401
    post.assert_not_called()


def test_returned_result_is_only_image_bytes_no_key():
    a = _adapter(key="nvapi-secret")
    with mock.patch.object(httpx.Client, "post",
                           return_value=_resp(200, json_body=_artifacts_ok())):
        out = a.generate(GenerationRequest(prompt="p", style=None, count=1))
    assert isinstance(out, list) and isinstance(out[0], bytes)
    assert b"nvapi-secret" not in out[0]


# ── Success ──────────────────────────────────────────────────────────────────

def test_success_returns_valid_png():
    a = _adapter()
    with mock.patch.object(httpx.Client, "post",
                           return_value=_resp(200, json_body=_artifacts_ok())):
        out = a.generate(GenerationRequest(prompt="p", style=None, count=1))
    assert Image.open(BytesIO(out[0])).format == "PNG"


# ── HTTP error taxonomy (status + retry classification preserved) ────────────

@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_non_retryable_http_errors_preserve_status(status):
    a = _adapter()
    with mock.patch.object(httpx.Client, "post", return_value=_resp(status, text="err")):
        with pytest.raises(AIProviderError) as ei:
            a.generate(GenerationRequest(prompt="p", style=None, count=1))
    assert ei.value.status_code == status


def test_429_is_retried_then_raised():
    a = _adapter()
    with mock.patch.object(httpx.Client, "post", return_value=_resp(429, text="rate")), \
         mock.patch("app.services.ai.nvidia_flux_adapter.time.sleep"):
        with pytest.raises(AIProviderError) as ei:
            a.generate(GenerationRequest(prompt="p", style=None, count=1))
    assert ei.value.status_code == 429


@pytest.mark.parametrize("status", [500, 502, 503])
def test_5xx_retries_bounded_then_raises(status):
    a = _adapter()
    calls = {"n": 0}

    def _post(url, json=None, headers=None):  # noqa: A002
        calls["n"] += 1
        return _resp(status, text="server error")

    with mock.patch.object(httpx.Client, "post", side_effect=_post), \
         mock.patch("app.services.ai.nvidia_flux_adapter.time.sleep"):
        with pytest.raises(AIProviderError) as ei:
            a.generate(GenerationRequest(prompt="p", style=None, count=1))
    # Bounded by NVIDIA_MAX_ATTEMPTS — never an unbounded retry storm.
    assert calls["n"] <= max(1, generation_service.__dict__.get("NVIDIA_MAX_ATTEMPTS", 2) or 2) + 1
    assert ei.value.status_code == status


@pytest.mark.parametrize("status", [503, 504])
def test_503_504_retries_bounded_then_raises(status):
    a = _adapter()
    calls = {"n": 0}

    def _post(url, json=None, headers=None):  # noqa: A002
        calls["n"] += 1
        return _resp(status, text="upstream gateway error")

    with mock.patch.object(httpx.Client, "post", side_effect=_post), \
         mock.patch("app.services.ai.nvidia_flux_adapter.time.sleep"):
        with pytest.raises(AIProviderError) as ei:
            a.generate(GenerationRequest(prompt="p", style=None, count=1))
    assert calls["n"] >= 2                 # retried at least once (bounded)
    assert calls["n"] <= 3                 # never an unbounded storm
    assert ei.value.status_code == status  # real upstream status preserved


def test_failure_log_is_sanitized_and_structured(caplog):
    a = _adapter(key="nvapi-SECRET")
    r = _resp(500, text="boom")
    r.headers = {"Nvcf-Reqid": "req-777"}
    with mock.patch.object(httpx.Client, "post", return_value=r), \
         mock.patch("app.services.ai.nvidia_flux_adapter.time.sleep"), \
         caplog.at_level("WARNING", logger="app.services.ai.nvidia_flux"):
        with pytest.raises(AIProviderError):
            a.generate(GenerationRequest(prompt="p", style=None, count=1,
                                         room_label="Living Area", generation_id="gen-1"))
    text = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "[AI][NVIDIA] generation failed" in text
    assert "status=500" in text and "attempt=" in text
    assert "room=Living Area" in text and "generation_id=gen-1" in text
    assert "control_image=False" in text
    assert "nvapi-SECRET" not in text     # key never logged


def test_timeout_returns_clear_timeout_error():
    a = _adapter()
    with mock.patch.object(httpx.Client, "post",
                           side_effect=httpx.TimeoutException("read timed out")), \
         mock.patch("app.services.ai.nvidia_flux_adapter.time.sleep"):
        with pytest.raises(AIProviderError) as ei:
            a.generate(GenerationRequest(prompt="p", style=None, count=1))
    assert ei.value.status_code == 504
    assert "TIMEOUT" in str(ei.value).upper()


# ── Malformed / invalid provider responses (never a fake success) ────────────

def test_malformed_200_non_json_raises():
    a = _adapter()
    r = _resp(200)
    r.json.side_effect = ValueError("not json")
    with mock.patch.object(httpx.Client, "post", return_value=r):
        with pytest.raises(Exception):  # noqa: B017 — any error, never a silent success
            a.generate(GenerationRequest(prompt="p", style=None, count=1))


def test_200_with_no_image_raises():
    a = _adapter()
    with mock.patch.object(httpx.Client, "post",
                           return_value=_resp(200, json_body={"artifacts": []})):
        with pytest.raises(AIProviderError):
            a.generate(GenerationRequest(prompt="p", style=None, count=1))


def test_200_with_undecodable_image_is_not_a_success():
    a = _adapter()
    bad = {"artifacts": [{"base64": "!!!not-base64!!!"}]}
    with mock.patch.object(httpx.Client, "post", return_value=_resp(200, json_body=bad)):
        with pytest.raises(Exception):  # noqa: B017 — decode failure, never a fake image
            a.generate(GenerationRequest(prompt="p", style=None, count=1))


# ── Log safety ───────────────────────────────────────────────────────────────

def test_safe_body_summary_redacts_base64_and_keys():
    leaky = '{"artifacts":[{"base64":"' + "A" * 200 + '"}]} nvapi-' + "z" * 80
    out = _safe_body_summary(leaky)
    assert "A" * 40 not in out
    assert "nvapi-" + "z" * 80 not in out
    assert "<redacted:base64>" in out


# ── Actionable, key-free provider errors (task 4) ────────────────────────────

def test_provider_error_carries_endpoint_elapsed_and_request_id():
    a = _adapter(key="nvapi-secret")
    r = _resp(500, text='{"error":"internal"}')
    r.headers = {"Nvcf-Reqid": "req-abc-123"}
    with mock.patch.object(httpx.Client, "post", return_value=r), \
         mock.patch("app.services.ai.nvidia_flux_adapter.time.sleep"):
        with pytest.raises(AIProviderError) as ei:
            a.generate(GenerationRequest(prompt="p", style=None, count=1))
    exc = ei.value
    assert exc.status_code == 500
    assert exc.endpoint == OFFICIAL_ENDPOINT
    assert exc.request_id == "req-abc-123"
    msg = str(exc)
    assert "req-abc-123" in msg and "endpoint=" in msg


def test_error_message_never_contains_api_key():
    # The adapter must never insert the configured key into any raised error,
    # for any status class.
    a = _adapter(key="nvapi-TOP-SECRET-KEY")
    for status in (401, 400, 500):
        r = _resp(status, text='{"error":"provider said no"}')
        r.headers = {}
        with mock.patch.object(httpx.Client, "post", return_value=r), \
             mock.patch("app.services.ai.nvidia_flux_adapter.time.sleep"):
            with pytest.raises(AIProviderError) as ei:
                a.generate(GenerationRequest(prompt="p", style=None, count=1))
        assert "nvapi-TOP-SECRET-KEY" not in str(ei.value)
        assert "nvapi-TOP-SECRET-KEY" not in repr(ei.value)


# ── BASE_GEOMETRY_INVALID does not gate a text-to-image render ────────────────

class _BaseModeWouldGenerate(AIProviderAdapter):
    """A text-to-image provider (no control image) that records if it was called."""

    name = "nvidia"
    model = "black-forest-labs/flux.1-dev"
    supports_control_image = False

    def __init__(self) -> None:
        self.called = False

    def generate(self, request: GenerationRequest) -> list[bytes]:
        self.called = True
        return [_png_bytes()]


class _BaseModeFailing(AIProviderAdapter):
    name = "nvidia"
    model = "black-forest-labs/flux.1-dev"
    supports_control_image = False

    def generate(self, request: GenerationRequest) -> list[bytes]:
        raise AIProviderError("nvidia", "NVIDIA HTTP 502: upstream", 502)


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


def test_text_to_image_renders_without_base_and_without_geometry_gate():
    # No base render AND geometry not "faithful": a text-to-image provider must
    # STILL render — the §L base gate only applies to control-image providers, so
    # BASE_GEOMETRY_INVALID must NOT be raised here.
    a = _BaseModeWouldGenerate()
    with mock.patch("app.services.generation_service.AI_DEMO_MODE", False):
        label, _png, *_ = _run(a, base_render=None, scene_faithful=False)
    assert a.called is True
    assert label == "Bedroom 1"


def test_text_to_image_failure_surfaces_real_provider_error_not_geometry():
    # A 502 from NVIDIA must surface as the real provider failure (status 502),
    # never masked as BASE_GEOMETRY_INVALID and never a fallback image.
    with mock.patch("app.services.generation_service.AI_DEMO_MODE", False):
        with pytest.raises(floor_plan_service.FloorPlanError) as ei:
            _run(_BaseModeFailing(), base_render=None, scene_faithful=True)
    assert ei.value.status_code == 502
    assert "BASE_GEOMETRY_INVALID" not in str(ei.value.detail)
    assert "502" in str(ei.value.detail)
