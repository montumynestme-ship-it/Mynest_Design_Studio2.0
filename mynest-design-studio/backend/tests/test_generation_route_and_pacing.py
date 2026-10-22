"""Full API/route flow + provider pacing regression tests for the NVIDIA render.

Covers the layers a direct isolated adapter call does NOT exercise:
  * the FastAPI route returns a usable 201 with the REAL structured provider error
    on total failure — it must never convert a completed-but-failed generation into
    a bare HTTP 500/502 (task 10/13);
  * the inter-room rate-limit delay is applied in TEXT-TO-IMAGE base mode (the bug
    where it was gated behind img2img and silently skipped — task 8/9);
  * multi-room generation is sequential by default (task 7);
  * the startup config log never leaks the API key (task 1-3).

Adapters are mocked, so no live NVIDIA call is made.
"""

import unittest.mock as mock

from fastapi.testclient import TestClient

from app.services import generation_service
from app.services.ai import registry
from app.services.ai.base import AIProviderError
from app.services.ai.mock_adapter import MockAdapter

FID = "f6b65d2b-4f96-4931-9f08-67dbd09776f6"


# ── Route flow: total failure stays a usable 201, never a false 500/502 ───────

def test_route_all_fail_returns_201_with_real_error_not_500():
    from app.main import app

    class AllFail(MockAdapter):
        def generate(self, request):
            raise AIProviderError(
                "nvidia", "NVIDIA generation failed: HTTP 500: Internal Server Error",
                502, "black-forest-labs/flux.1-dev",
                endpoint="https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.1-dev",
                elapsed=9.4, request_id="req-xyz",
            )

    with mock.patch.object(registry, "get_adapter", return_value=AllFail()):
        with TestClient(app) as client:
            r = client.post(f"/api/floor-plans/{FID}/generate", json={
                "provider": "nvidia", "count": 1,
                "design_intent": {"style": "modern"},
                "rooms": ["Living Area", "Kitchen"],
                "fresh_generation": True,
            })
    # The API layer must NOT convert this into a 500/502 — it returns a usable
    # record carrying the real provider error for the UI to display.
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "failed"
    assert body["images"] == []
    assert body["error"] and "500" in body["error"]
    assert body["room_errors"] and all(e["status"] == 502 for e in body["room_errors"])
    # Real, actionable diagnostics survive to the UI; the key never does.
    assert "NVIDIA_API_KEY" not in str(body)


def test_route_success_returns_201_and_stores_images():
    from app.main import app

    with mock.patch.object(registry, "get_adapter", return_value=MockAdapter()):
        with TestClient(app) as client:
            r = client.post(f"/api/floor-plans/{FID}/generate", json={
                "provider": "nvidia", "count": 1,
                "design_intent": {"style": "modern"},
                "rooms": ["Living Area", "Kitchen"],
                "fresh_generation": True,
            })
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "completed"
    labels = [im["label"] for im in body["images"]]
    assert labels == ["Living Area", "Kitchen"]
    for im in body["images"]:
        assert im["url"].endswith(tuple(f"/images/{i}" for i in range(len(body["images"]))))


# ── Provider pacing: the room delay is applied in base (text-to-image) mode ───

def test_room_delay_applied_in_base_mode():
    # MockAdapter.supports_control_image is False (base/text-to-image). With >1 room
    # and no failures, the inter-room rate-limit delay MUST be applied (previously it
    # was skipped in base mode, firing NVIDIA calls back-to-back → transient 5xx).
    slept: list[float] = []
    with mock.patch.object(registry, "get_adapter", return_value=MockAdapter()), \
         mock.patch.object(generation_service, "AI_DEMO_MODE", False), \
         mock.patch.object(generation_service, "AI_ROOM_DELAY_SECONDS", 4.0), \
         mock.patch.object(generation_service.time, "sleep", side_effect=slept.append):
        generation_service.generate(
            file_id=FID, provider="nvidia", count=1,
            design_intent={"style": "modern"},
            requested_rooms=["Living Area", "Kitchen"], fresh_generation=True,
        )
    # Exactly one 4s spacing between the two rooms (none before the first).
    assert slept.count(4.0) == 1


def test_no_room_delay_before_first_room_single_room():
    slept: list[float] = []
    with mock.patch.object(registry, "get_adapter", return_value=MockAdapter()), \
         mock.patch.object(generation_service, "AI_DEMO_MODE", False), \
         mock.patch.object(generation_service, "AI_ROOM_DELAY_SECONDS", 4.0), \
         mock.patch.object(generation_service.time, "sleep", side_effect=slept.append):
        generation_service.generate(
            file_id=FID, provider="nvidia", count=1,
            design_intent={"style": "modern"},
            requested_rooms=["Living Area"], fresh_generation=True,
        )
    assert 4.0 not in slept  # single room → no spacing delay


def test_delay_skipped_after_a_room_fails():
    # Once a room fails there is no successful call to space from, so we must not
    # keep sleeping the full delay for each remaining room.
    slept: list[float] = []

    class FailFirst(MockAdapter):
        def generate(self, request):
            if request.room_label == "Living Area":
                raise AIProviderError("nvidia", "HTTP 500", 502)
            return super().generate(request)

    with mock.patch.object(registry, "get_adapter", return_value=FailFirst()), \
         mock.patch.object(generation_service, "AI_DEMO_MODE", False), \
         mock.patch.object(generation_service, "AI_ROOM_DELAY_SECONDS", 4.0), \
         mock.patch.object(generation_service.time, "sleep", side_effect=slept.append):
        generation_service.generate(
            file_id=FID, provider="nvidia", count=1,
            design_intent={"style": "modern"},
            requested_rooms=["Living Area", "Kitchen"], fresh_generation=True,
        )
    assert 4.0 not in slept  # first room failed → no spacing for the rest


def test_no_provider_delay_in_demo_mode():
    slept: list[float] = []
    with mock.patch.object(registry, "get_adapter", return_value=MockAdapter()), \
         mock.patch.object(generation_service, "AI_DEMO_MODE", True), \
         mock.patch.object(generation_service, "AI_ROOM_DELAY_SECONDS", 4.0), \
         mock.patch.object(generation_service.time, "sleep", side_effect=slept.append):
        generation_service.generate(
            file_id=FID, provider="nvidia", count=1,
            design_intent={"style": "modern"},
            requested_rooms=["Living Area", "Kitchen"], fresh_generation=True,
        )
    assert 4.0 not in slept  # demo/mock mode → no provider rate-limit delay


# ── control_image is actually passed from the service to the adapter ──────────

def test_control_image_is_passed_to_adapter():
    from io import BytesIO

    from PIL import Image

    from app.services.ai.base import AIProviderAdapter, GenerationRequest

    def _png(fill=(200, 180, 150)) -> bytes:
        # Non-blank structured image (the post-AI gate rejects blank output).
        b = BytesIO()
        img = Image.new("RGB", (16, 16), fill)
        for y in range(8):
            for x in range(16):
                img.putpixel((x, y), (30, 40, 60))
        img.save(b, "PNG")
        return b.getvalue()

    captured: dict = {}

    class CapturingAdapter(AIProviderAdapter):
        name = "nvidia"
        model = "black-forest-labs/flux.1-dev"
        supports_control_image = True  # img2img-capable → gate active, base required

        def generate(self, request: GenerationRequest):
            captured["control_image"] = request.control_image
            # Output distinct from the base so the post-AI gate (restyle-no-op reject)
            # passes — this test asserts the base render reaches the adapter.
            return [_png((90, 160, 110))]

    canonical = {"furniture": [
        {"uid": "b", "item_id": "bed", "cx": 500, "cy": 350, "w": 1800, "h": 2000, "rotation": 0},
    ]}
    base = _png()
    with mock.patch("app.services.generation_service.AI_DEMO_MODE", False):
        generation_service._render_room(
            CapturingAdapter(), "nvidia", "Modern", ("Bedroom 1", "p", 1024, 768),
            ("proj", "fp", canonical, None),
            generation_id="g", index=0, seed=1, fresh_generation=True,
            base_render=base, scene_geometry_faithful=True,
        )
    assert captured["control_image"] == base  # the validated base render reaches the adapter


# ── Cache semantics: fresh bypasses, non-fresh may reuse ─────────────────────

def _cache_probe_adapter():
    from app.services.ai.base import AIProviderAdapter, GenerationRequest
    from io import BytesIO
    from PIL import Image

    calls = {"n": 0}

    class Probe(AIProviderAdapter):
        name = "nvidia"
        model = "black-forest-labs/flux.1-dev"
        supports_control_image = False  # base/text-to-image → no gate

        def generate(self, request: GenerationRequest):
            import os
            calls["n"] += 1
            b = BytesIO()
            # Noise so the encoded PNG exceeds the cache's >1000-byte floor.
            img = Image.frombytes("RGB", (128, 128), os.urandom(128 * 128 * 3))
            img.save(b, "PNG")
            return [b.getvalue()]

    return Probe(), calls


def test_fresh_generation_bypasses_cache():
    adapter, calls = _cache_probe_adapter()
    canonical = {"furniture": [
        {"uid": "u-fresh", "item_id": "bed", "cx": 1, "cy": 2, "w": 30, "h": 40, "rotation": 0},
    ]}
    ctx = ("proj", "fp", canonical, None)
    with mock.patch("app.services.generation_service.AI_DEMO_MODE", False):
        for _ in range(2):
            _label, _png, _prov, _m, _s, cache_hit, *_ = generation_service._render_room(
                adapter, "nvidia", "Modern", ("Kitchen", "p", 1024, 768), ctx,
                generation_id="g", index=0, seed=1, fresh_generation=True,
                base_render=None, scene_geometry_faithful=True,
            )
            assert cache_hit is False
    assert calls["n"] == 2  # fresh always calls the provider, never the cache


def test_non_fresh_generation_uses_cache():
    adapter, calls = _cache_probe_adapter()
    canonical = {"furniture": [
        {"uid": "u-cache", "item_id": "bed", "cx": 3, "cy": 4, "w": 30, "h": 40, "rotation": 0},
    ]}
    ctx = ("proj", "fp", canonical, None)
    with mock.patch("app.services.generation_service.AI_DEMO_MODE", False):
        # First fresh run populates the cache.
        generation_service._render_room(
            adapter, "nvidia", "Modern", ("Kitchen", "p", 1024, 768), ctx,
            generation_id="g", index=0, seed=1, fresh_generation=True,
            base_render=None, scene_geometry_faithful=True,
        )
        # Second, non-fresh run must HIT the cache and NOT call the provider again.
        _label, _png, _prov, _m, _s, cache_hit, *_ = generation_service._render_room(
            adapter, "nvidia", "Modern", ("Kitchen", "p", 1024, 768), ctx,
            generation_id="g", index=1, seed=2, fresh_generation=False,
            base_render=None, scene_geometry_faithful=True,
        )
    assert cache_hit is True
    assert calls["n"] == 1  # provider called once; second served from cache


# ── Sequential by default ─────────────────────────────────────────────────────

def test_multi_room_generation_is_sequential_by_default():
    order: list[str] = []

    class Recorder(MockAdapter):
        def generate(self, request):
            order.append(request.room_label)
            return super().generate(request)

    with mock.patch.object(registry, "get_adapter", return_value=Recorder()), \
         mock.patch.object(generation_service, "AI_DEMO_MODE", False), \
         mock.patch.object(generation_service, "AI_ROOM_DELAY_SECONDS", 0.0):
        resp = generation_service.generate(
            file_id=FID, provider="nvidia", count=1,
            design_intent={"style": "modern"},
            requested_rooms=["Living Area", "Kitchen", "Dining Area"],
            fresh_generation=True,
        )
    assert order == ["Living Area", "Kitchen", "Dining Area"]  # strict order
    assert [im.label for im in resp.images] == order


# ── Startup config log never leaks the key ────────────────────────────────────

def test_startup_config_log_omits_api_key(caplog):
    import app.main as main_mod

    with mock.patch.object(main_mod.ai_config, "NVIDIA_API_KEY", "nvapi-DO-NOT-LOG"):
        with caplog.at_level("INFO", logger="uvicorn.error"):
            main_mod._log_effective_ai_config()
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "nvapi-DO-NOT-LOG" not in text
    assert "api_key_present=True" in text
    assert "provider=" in text and "img2img_requested=" in text and "endpoint=" in text
