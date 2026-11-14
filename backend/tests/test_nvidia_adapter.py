"""NVIDIA-hosted Flux (the only provider) adapter + generation-gate tests."""

import base64
from io import BytesIO
from unittest import mock

import httpx
import pytest
from PIL import Image

from app.services import generation_service
from app.services.ai import registry
from app.services.ai.base import AIProviderAdapter, AIProviderError, GenerationRequest
from app.services.ai.nvidia_flux_adapter import NvidiaFluxAdapter


def _png_bytes(color=(200, 180, 150)) -> bytes:
    img = Image.new("RGB", (16, 16), color)
    for y in range(8):
        for x in range(16):
            img.putpixel((x, y), (30, 40, 60))
    buf = BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _blank_png() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (16, 16), (0, 0, 0)).save(buf, "PNG")
    return buf.getvalue()


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _resp(status: int, *, json_body=None, content=None, text="") -> mock.Mock:
    r = mock.Mock()
    r.status_code = status
    r.json.return_value = json_body or {}
    r.content = content if content is not None else b""
    r.text = text
    r.headers = {}
    r.request = mock.Mock()
    return r


def _artifacts_ok() -> dict:
    return {"artifacts": [{"base64": _b64(_png_bytes())}]}


# A self-hosted NIM base: arbitrary image input is only genuinely supported off the
# hosted API, so img2img-send tests must point at a NIM to pass the deployment gate.
_NIM_BASE = "http://nim-host:8000"


def _adapter(
    *, key="nvapi-secret", img2img=False, model="black-forest-labs/flux.1-dev",
    base="https://ai.api.nvidia.com/v1/genai",
) -> NvidiaFluxAdapter:
    with mock.patch("app.services.ai.nvidia_flux_adapter.NVIDIA_API_KEY", key):
        with mock.patch("app.services.ai.nvidia_flux_adapter.NVIDIA_SUPPORTS_IMG2IMG", img2img):
            with mock.patch("app.services.ai.nvidia_flux_adapter.NVIDIA_IMAGE_MODEL", model):
                with mock.patch("app.services.ai.nvidia_flux_adapter.NVIDIA_API_BASE", base):
                    return NvidiaFluxAdapter()


# ── Registry: NVIDIA is the ONLY provider ────────────────────────────────────

def test_registered_image_providers() -> None:
    # NVIDIA (text-to-image) and fal.ai FLUX.1 Kontext (image editing) are the two
    # real providers; removed experimental providers stay gone.
    assert isinstance(registry.get_adapter("nvidia"), NvidiaFluxAdapter)
    from app.services.ai.fal_flux_adapter import FalFluxAdapter
    assert isinstance(registry.get_adapter("fal"), FalFluxAdapter)
    for gone in ("flux", "flux-free", "pollinations", "gemini", "bfl"):
        assert gone not in registry._ADAPTERS


def test_validate_provider_nvidia_hides_key_and_reports_config() -> None:
    # Request nvidia explicitly (the default provider may be fal).
    with mock.patch("app.services.ai.registry.NVIDIA_API_KEY", "nvapi-secret"):
        res = registry.validate_provider("nvidia")
    assert res["provider"] == "nvidia"
    assert res["status"] == "READY"
    assert "nvapi-secret" not in str(res)
    with mock.patch("app.services.ai.registry.NVIDIA_API_KEY", ""):
        assert registry.validate_provider("nvidia")["status"] == "NOT_CONFIGURED"


# ── Adapter behavior (HTTP mocked) ───────────────────────────────────────────

def test_nvidia_success_returns_png() -> None:
    adapter = _adapter()
    with mock.patch.object(httpx.Client, "post", return_value=_resp(200, json_body=_artifacts_ok())):
        out = adapter.generate(GenerationRequest(prompt="a room", style="Modern", count=1))
    assert Image.open(BytesIO(out[0])).size == (16, 16)


def test_nvidia_missing_key_raises_401() -> None:
    adapter = _adapter(key="")
    with pytest.raises(AIProviderError) as ei:
        adapter.generate(GenerationRequest(prompt="p", style=None, count=1))
    assert ei.value.status_code == 401


def test_nvidia_401_auth_error() -> None:
    adapter = _adapter()
    with mock.patch.object(httpx.Client, "post", return_value=_resp(401, text="unauthorized")):
        with pytest.raises(AIProviderError) as ei:
            adapter.generate(GenerationRequest(prompt="p", style=None, count=1))
    assert ei.value.status_code == 401


def test_nvidia_429_rate_limit() -> None:
    adapter = _adapter()
    with mock.patch.object(httpx.Client, "post", return_value=_resp(429, text="rate")):
        with mock.patch("app.services.ai.nvidia_flux_adapter.time.sleep"):
            with pytest.raises(AIProviderError) as ei:
                adapter.generate(GenerationRequest(prompt="p", style=None, count=1))
    assert ei.value.status_code == 429


def test_nvidia_404_model_unavailable() -> None:
    adapter = _adapter()
    with mock.patch.object(httpx.Client, "post", return_value=_resp(404, text="not found")):
        with pytest.raises(AIProviderError) as ei:
            adapter.generate(GenerationRequest(prompt="p", style=None, count=1))
    assert ei.value.status_code == 404


def test_nvidia_400_invalid_request() -> None:
    adapter = _adapter()
    with mock.patch.object(httpx.Client, "post", return_value=_resp(400, text="bad")):
        with pytest.raises(AIProviderError) as ei:
            adapter.generate(GenerationRequest(prompt="p", style=None, count=1))
    assert ei.value.status_code == 400


def test_nvidia_500_server_error_retries_then_fails() -> None:
    adapter = _adapter()
    with mock.patch.object(httpx.Client, "post", return_value=_resp(500, text="boom")):
        with mock.patch("app.services.ai.nvidia_flux_adapter.time.sleep"):
            with pytest.raises(AIProviderError):
                adapter.generate(GenerationRequest(prompt="p", style=None, count=1))


def test_nvidia_missing_image_raises() -> None:
    adapter = _adapter()
    with mock.patch.object(httpx.Client, "post", return_value=_resp(200, json_body={"artifacts": []})):
        with pytest.raises(AIProviderError):
            adapter.generate(GenerationRequest(prompt="p", style=None, count=1))


def test_nvidia_text_to_image_by_default_sends_no_image() -> None:
    adapter = _adapter(img2img=False)
    assert adapter.supports_control_image is False
    captured = {}

    def _post(url, json=None, headers=None):  # noqa: A002
        captured["json"] = json
        captured["headers"] = headers
        return _resp(200, json_body=_artifacts_ok())

    with mock.patch.object(httpx.Client, "post", side_effect=_post):
        adapter.generate(GenerationRequest(prompt="ROOM", style=None, count=1, control_image=_png_bytes()))
    assert "image" not in captured["json"]  # no img2img on the text-to-image model
    assert captured["headers"]["Authorization"].startswith("Bearer ")


def test_nvidia_img2img_sends_controlnet_canny_request_when_enabled() -> None:
    # An image-guided-capable model AND a self-hosted NIM are required for a real
    # img2img request: flux.1-dev is text-to-image only, and the hosted API rejects
    # arbitrary images regardless of model.
    adapter = _adapter(img2img=True, model="black-forest-labs/flux.1-canny-dev", base=_NIM_BASE)
    assert adapter.supports_control_image is True
    assert adapter.mode == "canny"  # default control mode
    base = _png_bytes((10, 20, 30))
    captured = {}

    def _post(url, json=None, headers=None):  # noqa: A002
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _resp(200, json_body=_artifacts_ok())

    # The base render is a base64 data URI — the valid mechanism on a self-hosted NIM
    # (arbitrary-image-capable). The hosted Preview API path is gated separately.
    with mock.patch(
        "app.services.ai.nvidia_flux_adapter.NVIDIA_ARBITRARY_IMAGE_SUPPORTED", True
    ), mock.patch.object(httpx.Client, "post", side_effect=_post):
        adapter.generate(GenerationRequest(prompt="ROOM SPEC", style=None, count=1, control_image=base))
    body = captured["json"]
    assert body["image"].startswith("data:image/png;base64,")
    assert body["mode"] == "canny"
    assert body["preprocess_image"] is True
    # The hosted API rejects response_format and width/height in img2img.
    assert "response_format" not in body
    assert "width" not in body and "height" not in body
    # The §5 geometry-lock preamble leads the prompt (installed _IMG2IMG_PREAMBLE).
    assert "STRICT GEOMETRY LOCK" in body["prompt"]  # img2img geometry-preservation preamble present
    assert "nvapi-secret" not in captured["url"]
    assert captured["headers"]["Authorization"] == "Bearer nvapi-secret"


def test_nvidia_img2img_depth_mode_uses_depth_control() -> None:
    with mock.patch("app.services.ai.nvidia_flux_adapter.NVIDIA_API_KEY", "nvapi-secret"):
        with mock.patch("app.services.ai.nvidia_flux_adapter.NVIDIA_SUPPORTS_IMG2IMG", True):
            with mock.patch("app.services.ai.nvidia_flux_adapter.NVIDIA_IMG2IMG_MODE", "depth"):
                with mock.patch(
                    "app.services.ai.nvidia_flux_adapter.NVIDIA_IMAGE_MODEL",
                    "black-forest-labs/flux.1-depth-dev",  # depth-capable model
                ):
                    with mock.patch(
                        "app.services.ai.nvidia_flux_adapter.NVIDIA_API_BASE", _NIM_BASE,
                    ):  # arbitrary image input requires a self-hosted NIM
                        adapter = NvidiaFluxAdapter()
    assert adapter.mode == "depth"
    captured = {}

    def _post(url, json=None, headers=None):  # noqa: A002
        captured["json"] = json
        return _resp(200, json_body=_artifacts_ok())

    with mock.patch(
        "app.services.ai.nvidia_flux_adapter.NVIDIA_ARBITRARY_IMAGE_SUPPORTED", True
    ), mock.patch.object(httpx.Client, "post", side_effect=_post):
        adapter.generate(GenerationRequest(prompt="p", style=None, count=1, control_image=_png_bytes()))
    assert captured["json"]["mode"] == "depth"
    assert captured["json"]["preprocess_image"] is True
    assert captured["json"]["image"].startswith("data:image/png;base64,")


def test_nvidia_text_to_image_sends_width_height_not_image() -> None:
    adapter = _adapter(img2img=False)
    captured = {}

    def _post(url, json=None, headers=None):  # noqa: A002
        captured["json"] = json
        return _resp(200, json_body=_artifacts_ok())

    with mock.patch.object(httpx.Client, "post", side_effect=_post):
        adapter.generate(GenerationRequest(prompt="p", style=None, count=1, width=1024, height=768))
    assert "image" not in captured["json"]
    assert captured["json"]["width"] == 1024
    assert captured["json"]["height"] == 768


# ── Generation hard gate / no fallback (pure _render_room) ───────────────────

class _WouldGenerate(AIProviderAdapter):
    name = "nvidia"
    model = "black-forest-labs/flux.1-dev"
    supports_control_image = True

    def __init__(self) -> None:
        self.called = False

    def generate(self, request: GenerationRequest) -> list[bytes]:
        self.called = True
        # Distinct from the base render so the post-AI geometry gate (which rejects a
        # restyle no-op that is ~identical to the base) passes — this test asserts the
        # adapter IS invoked when geometry is valid, not output fidelity.
        return [_png_bytes(color=(90, 160, 110))]


class _Failing(AIProviderAdapter):
    name = "nvidia"
    model = "black-forest-labs/flux.1-dev"
    supports_control_image = True

    def generate(self, request: GenerationRequest) -> list[bytes]:
        raise AIProviderError("nvidia", "simulated outage", 503)


# A canonical scene with real Bedroom 1 furniture, so the §2 manifest gate passes
# and the OTHER gate conditions (base present/valid, scene faithful) are exercised.
_BEDROOM_CANONICAL = {
    "furniture": [
        {"uid": "b", "item_id": "bed", "cx": 500, "cy": 350, "w": 1800, "h": 2000, "rotation": 0},
        {"uid": "s", "item_id": "side-table", "cx": 300, "cy": 350, "w": 450, "h": 450, "rotation": 0},
    ]
}


def _run(adapter, *, base_render, scene_faithful=True, canonical=_BEDROOM_CANONICAL):
    return generation_service._render_room(
        adapter, "nvidia", "Modern", ("Bedroom 1", "p", 1024, 768),
        ("proj", "fp", canonical, None),
        generation_id="g", index=0, seed=1, fresh_generation=True,
        base_render=base_render, scene_geometry_faithful=scene_faithful,
    )


def test_gate_no_base_never_calls_nvidia() -> None:
    from app.services import floor_plan_service
    a = _WouldGenerate()
    with mock.patch("app.services.generation_service.AI_DEMO_MODE", False):
        with pytest.raises(floor_plan_service.FloorPlanError):
            _run(a, base_render=None)
    assert a.called is False


def test_gate_invalid_scene_never_calls_nvidia() -> None:
    from app.services import floor_plan_service
    a = _WouldGenerate()
    with mock.patch("app.services.generation_service.AI_DEMO_MODE", False):
        with pytest.raises(floor_plan_service.FloorPlanError):
            _run(a, base_render=_png_bytes(), scene_faithful=False)
    assert a.called is False


def test_gate_blank_base_never_calls_nvidia() -> None:
    from app.services import floor_plan_service
    a = _WouldGenerate()
    with mock.patch("app.services.generation_service.AI_DEMO_MODE", False):
        with pytest.raises(floor_plan_service.FloorPlanError):
            _run(a, base_render=_blank_png())
    assert a.called is False


def test_gate_valid_calls_nvidia() -> None:
    a = _WouldGenerate()
    with mock.patch("app.services.generation_service.AI_DEMO_MODE", False):
        label, _png, *_ = _run(a, base_render=_png_bytes())
    assert a.called is True
    assert label == "Bedroom 1"


def test_nvidia_failure_never_falls_back_to_deterministic_or_pollinations() -> None:
    from app.services import floor_plan_service
    with mock.patch("app.services.generation_service.AI_DEMO_MODE", False):
        with pytest.raises(floor_plan_service.FloorPlanError):
            _run(_Failing(), base_render=_png_bytes())


def test_geometry_hash_covers_walls_doors_windows_furniture() -> None:
    bed = {"uid": "b", "item_id": "bed", "cx": 1, "cy": 2, "w": 3, "h": 4, "rotation": 0}
    base = {"furniture": [bed]}
    h0 = generation_service._geometry_hash(base)
    assert generation_service._geometry_hash({"furniture": [{**bed, "cx": 9}]}) != h0
    assert generation_service._geometry_hash({**base, "structured_walls": [{"id": "w"}]}) != h0
    assert generation_service._geometry_hash({**base, "doors": [{"id": "d"}]}) != h0
    assert generation_service._geometry_hash({**base, "windows": [{"id": "win"}]}) != h0


def test_nvidia_diagnostics_logging_records_all_twenty_fields_safely() -> None:
    adapter = _adapter(
        key="secret-api-key-12345", img2img=True,
        model="black-forest-labs/flux.1-canny-dev",  # image-guided-capable model
        base=_NIM_BASE,                               # on a self-hosted NIM
    )
    logged_diagnostics = {}

    def _capture_log(**kwargs):
        logged_diagnostics.update(kwargs)

    with mock.patch(
        "app.services.ai.nvidia_flux_adapter.NVIDIA_ARBITRARY_IMAGE_SUPPORTED", True
    ), mock.patch.object(NvidiaFluxAdapter, "_log_diagnostics", side_effect=_capture_log):
        with mock.patch.object(httpx.Client, "post", return_value=_resp(200, json_body=_artifacts_ok())):
            adapter.generate(GenerationRequest(
                prompt="photorealistic living room",
                style=None,
                count=1,
                room_label="Living Area",
                room_id="room_0_Living Area",
                control_image=_png_bytes(),
            ))

    expected_fields = [
        "room_id", "room_label", "model", "endpoint", "prompt_length",
        "base_png_dimensions", "base_png_byte_size", "asset_upload_started",
        "asset_upload_success", "asset_id_present", "request_started_at",
        "request_timeout_seconds", "mode", "steps", "width", "height",
        "cfg_scale", "http_status", "body_summary", "request_duration",
        "retry_number",
    ]
    for field in expected_fields:
        assert field in logged_diagnostics, f"Missing field: {field}"

    assert logged_diagnostics["room_label"] == "Living Area"
    assert logged_diagnostics["room_id"] == "room_0_Living Area"
    assert logged_diagnostics["http_status"] == 200
    # Crucial security invariants: NEVER log keys or base64 data
    diag_str = str(logged_diagnostics)
    assert "secret-api-key-12345" not in diag_str
    assert "base64," not in diag_str

