"""Production NVIDIA image-conditioned path: the hosted Preview API accepts only
predefined example images, so an arbitrary room render must fail with a CLEAR
NVIDIA_ARBITRARY_IMAGE_UNSUPPORTED status (not a misleading 500/422) and never leak
the API key. Verified live: hosted flux.1-dev returns HTTP 422 'Expected:
example_id, got: base64' for a real base64 image.
"""

import app.core.config as cfg
from app.services.ai.base import AIProviderError, GenerationRequest
from app.services.ai.nvidia_flux_adapter import NvidiaFluxAdapter

_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 300


def _req():
    return GenerationRequest(
        prompt="living room", style=None, count=1, width=1024, height=1024, seed=0,
        control_image=_PNG,
    )


def test_hosted_arbitrary_image_refused_clearly(monkeypatch):
    # Default (hosted Preview API): arbitrary image unsupported.
    monkeypatch.setattr(
        "app.services.ai.nvidia_flux_adapter.NVIDIA_ARBITRARY_IMAGE_SUPPORTED", False
    )
    a = NvidiaFluxAdapter()
    a.supports_control_image = True
    try:
        a.generate(_req())
        raise AssertionError("expected AIProviderError, generate() returned")
    except AIProviderError as e:
        msg = str(e)
        assert e.status_code == 422
        assert "NVIDIA_ARBITRARY_IMAGE_UNSUPPORTED" in msg
        # documents the required self-hosted NIM deployment + endpoint
        assert "self-hosted" in msg and "/v1/infer" in msg
        # never leaks the key
        if cfg.NVIDIA_API_KEY:
            assert cfg.NVIDIA_API_KEY not in msg


def test_no_api_key_is_auth_error(monkeypatch):
    a = NvidiaFluxAdapter()
    a.api_key = ""
    try:
        a.generate(_req())
        raise AssertionError("expected AIProviderError")
    except AIProviderError as e:
        assert e.status_code == 401
