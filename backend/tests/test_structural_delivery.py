"""End-to-end (offline) proof that the correct STRUCTURAL REFERENCE reaches the AI provider.

The adapter/pairing/validation units are covered elsewhere; this closes the one remaining
gap — the SERVICE-level delivery link. It drives the real ``generation_service._render_room``
with a supplied, already-validated ``structural_render`` and a recording fake adapter, and
proves the structural bytes arrive at the provider boundary as
``GenerationRequest.structural_image``. A second test closes the loop with the REAL
``FalFluxAdapter``: that same structural image becomes the provider request's Canny
``control_lora_image_url`` when the opt-in flag is enabled.

No HTTP, no fal/paid call, no config-file or env change (flags are patched test-locally only),
no DB writes, no deterministic-geometry change. File-writing side effects are stubbed so the
test leaves no artifacts.
"""

import io
from unittest import mock

import pytest
from PIL import Image, ImageDraw

import app.services.generation_service as gs
from app.services.ai.base import GenerationRequest
from app.services.ai.fal_flux_adapter import FalFluxAdapter

_ADAPTER = "app.services.ai.fal_flux_adapter"


def _png(w: int, h: int, color: tuple[int, int, int]) -> bytes:
    """A NON-uniform PNG (two regions) so it passes the base/output blank gate
    (`_is_blank` rejects near-uniform frames: spread < 6)."""
    im = Image.new("RGB", (w, h), color)
    dark = tuple(max(0, c - 110) for c in color)
    ImageDraw.Draw(im).rectangle([w // 4, h // 4, 3 * w // 4, 3 * h // 4], fill=dark)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


class _RecordingAdapter:
    """Minimal fake provider adapter — records the request it is asked to generate."""

    name = "fal"
    model = "fal-ai/flux-control-lora-canny"
    supports_control_image = True
    last_conditioning_mode = "canny_controlnet"
    last_structural_image_sha256 = None
    last_control_source = "structural"
    last_control_image_sha256 = None
    last_request_id = None
    last_endpoint = None
    last_control_strength = 1.0
    last_effective_prompt = None

    def __init__(self, out_png: bytes) -> None:
        self._out = out_png
        self.captured: GenerationRequest | None = None

    def generate(self, request: GenerationRequest):  # noqa: D401
        self.captured = request
        return [self._out]


@pytest.fixture
def _stub_side_effects(monkeypatch):
    """No-op every file/DB side effect of _render_room so the test is pure + artifact-free."""
    for fn in (
        "_persist_base_render", "_save_debug_artifacts", "_save_cached_render",
        "_write_cache_provenance", "_write_room_manifest",
    ):
        monkeypatch.setattr(gs, fn, lambda *a, **k: None)
    monkeypatch.setattr(
        gs.base_inventory_service, "assess_section_base_inventory",
        lambda *a, **k: ("MATCH", {}),
    )
    monkeypatch.setattr(gs.furniture_manifest, "binding", lambda m: {})
    monkeypatch.setattr(gs.furniture_manifest, "expected_inventory", lambda m: {})


def _call_render_room(adapter, *, structural_render: bytes | None):
    base_png = _png(1216, 832, (210, 210, 210))     # non-blank deterministic base
    # explicit_manifest bypasses canonical re-grouping; furniture_count>0 clears ROOM_EMPTY.
    manifest = {"room_label": "Bedroom 1", "furniture_count": 1,
                "counts": {"Bed": 1}, "items": [{"uid": "b1", "item_id": "bed", "name": "Bed"}]}
    return gs._render_room(
        adapter, "fal", None,
        ("Bedroom 1", "ROOM: Bedroom 1.\nINVENTORY: 1x Bed.", 1216, 832),
        ("proj-1", "fp-1", {"furniture": [{"uid": "b1", "item_id": "bed"}]}, {"style": "Modern"}),
        "gen-1", 0, 7,
        fresh_generation=True,
        base_render=base_png,
        scene_geometry_faithful=True,
        structural_render=structural_render,
        explicit_manifest=manifest,
    ), base_png


def test_render_room_delivers_structural_image_to_provider(_stub_side_effects):
    """When a validated structural render is supplied, _render_room hands it to the provider
    (adapter.generate) as GenerationRequest.structural_image — the structural reference reaches
    the AI provider."""
    struct = _png(1216, 832, (0, 0, 0))             # distinct structural edge-map bytes
    adapter = _RecordingAdapter(out_png=_png(1216, 832, (40, 90, 160)))  # distinct output
    (_result, base_png) = _call_render_room(adapter, structural_render=struct)

    assert adapter.captured is not None, "adapter.generate was never called"
    # The STRUCTURAL reference reached the provider boundary (adapter.generate):
    assert adapter.captured.structural_image == struct
    assert adapter.captured.control_image == base_png     # base render = authoritative control


def test_render_room_without_structural_sends_none(_stub_side_effects):
    """Fallback preserved: no structural render → structural_image is None (edit/base baseline)."""
    adapter = _RecordingAdapter(out_png=_png(1216, 832, (40, 90, 160)))
    _call_render_room(adapter, structural_render=None)
    assert adapter.captured is not None
    assert adapter.captured.structural_image is None


def test_delivered_structural_becomes_canny_control_when_enabled():
    """Loop-closing: the EXACT structural image the service delivers becomes the provider
    request's Canny `control_lora_image_url` when the opt-in flag is on (real adapter, no
    HTTP)."""
    struct_uri = "data:image/png;base64,U1RSVUNU"
    base_uri = "data:image/png;base64,QkFTRQ=="
    req = GenerationRequest(
        prompt="ROOM: Bedroom 1.\nINVENTORY: 1x Bed.", style=None, count=1,
        width=1216, height=832, seed=7, room_label="Bedroom 1",
        control_image=b"base", structural_image=b"struct",
    )
    with mock.patch(f"{_ADAPTER}.FAL_CONTROL_STRUCTURAL", True):
        adapter = FalFluxAdapter()
        body = adapter._build_control_body(req, base_uri, 1216, 832, struct_uri)
    # The structural edge map is the Canny structure control; base render is the colour init:
    assert body["control_lora_image_url"] == struct_uri
    assert body.get("image_url") == base_uri
    assert adapter.last_control_source == "structural"


def test_generate_places_structural_in_outbound_provider_request(monkeypatch):
    """Strongest offline proof: the REAL ``FalFluxAdapter.generate()``, through the REAL Canny
    control path, puts the STRUCTURAL edge map into the ACTUAL outbound HTTP request body
    (``client.post(..., json=body)``) sent to the provider's Canny endpoint. Only the network
    socket is mocked — never a paid call; flags are patched test-locally, not in config."""
    from app.services.ai import fal_flux_adapter as FA

    captured: dict = {}

    class _Resp:
        status_code = 200
        headers: dict = {}

        def json(self):  # empty → queue resolution fails AFTER the body is already sent
            return {}

    class _Client:
        def __init__(self, *a, **k) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, endpoint, json=None, headers=None):
            captured["endpoint"] = endpoint
            captured["body"] = json
            return _Resp()

        def get(self, *a, **k):
            return _Resp()

    monkeypatch.setattr(FA.httpx, "Client", _Client)
    monkeypatch.setattr(FA, "FAL_USE_CONTROLNET", True)
    monkeypatch.setattr(FA, "FAL_CONTROL_STRUCTURAL", True)

    base = _png(1216, 832, (210, 210, 210))
    struct = _png(1216, 832, (12, 200, 12))
    adapter = FA.FalFluxAdapter()
    adapter.api_key = "test-key"
    adapter.arbitrary_image_effective = True
    req = GenerationRequest(
        prompt="ROOM: Bedroom 1.\nINVENTORY: 1x Bed.", style=None, count=1,
        width=1216, height=832, seed=7, room_label="Bedroom 1",
        control_image=base, structural_image=struct,
    )
    try:
        adapter.generate(req)  # queue resolution fails after the POST; the body is captured
    except Exception:  # noqa: BLE001 — we only assert on the captured outbound request
        pass

    body = captured.get("body")
    assert body is not None, "no outbound provider request was sent"
    assert "flux-control-lora-canny" in captured["endpoint"]           # Canny control endpoint
    assert body["control_lora_image_url"].startswith("data:image/png;base64,")
    assert body["image_url"].startswith("data:image/png;base64,")
    # The Canny STRUCTURE control is the structural edge map, DISTINCT from the base colour init:
    assert body["control_lora_image_url"] != body["image_url"]
    assert adapter.last_control_source == "structural"
