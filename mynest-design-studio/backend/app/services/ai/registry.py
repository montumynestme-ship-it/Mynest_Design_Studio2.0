from typing import Any

from app.core.config import (
    DEFAULT_AI_PROVIDER,
    FAL_IMAGE_MODEL,
    FAL_KEY,
    NVIDIA_API_KEY,
    NVIDIA_IMAGE_MODEL,
)
from app.services.ai.base import AIProviderAdapter
from app.services.ai.fal_flux_adapter import FalFluxAdapter
from app.services.ai.mock_adapter import MockAdapter
from app.services.ai.nvidia_flux_adapter import NvidiaFluxAdapter

# Image-generation providers. NVIDIA-hosted Flux is text-to-image only (its hosted
# endpoints reject an arbitrary uploaded image). fal.ai FLUX.1 Kontext is a hosted
# image-EDITING provider that accepts an arbitrary input image, so it is used for
# geometry-preserving restyle/edit. MockAdapter stays for AI_DEMO_MODE and tests.
_ADAPTERS: dict[str, type[AIProviderAdapter]] = {
    "nvidia": NvidiaFluxAdapter,
    "nvidia-flux": NvidiaFluxAdapter,
    "fal": FalFluxAdapter,
    "fal-flux": FalFluxAdapter,
    "fal-kontext": FalFluxAdapter,  # back-compat alias
    "demo": MockAdapter,
    "mock": MockAdapter,
}


def get_adapter(name: str | None = None) -> AIProviderAdapter:
    provider_name = (name or DEFAULT_AI_PROVIDER).lower()
    factory = _ADAPTERS.get(provider_name, NvidiaFluxAdapter)
    return factory()


def demo_adapter() -> AIProviderAdapter:
    return MockAdapter()


def validate_provider(name: str | None = None) -> dict[str, Any]:
    """Validate provider configuration (no live/billed call).

    Returns {provider, status, model, message}. Status is one of
    READY | NOT_CONFIGURED | AUTH_ERROR | PROVIDER_ERROR.
    """
    provider_name = (name or DEFAULT_AI_PROVIDER).lower()
    if provider_name in ("demo", "mock"):
        return {
            "provider": "demo",
            "status": "READY",
            "model": "mynest-demo-render",
            "message": "Demo mode is active (deterministic placeholder renderer)",
        }
    # fal.ai FLUX Kontext image editing — validates FAL_KEY (no live/billed call).
    if provider_name in ("fal", "fal-flux", "fal-kontext"):
        if not FAL_KEY:
            return {
                "provider": "fal",
                "status": "NOT_CONFIGURED",
                "model": FAL_IMAGE_MODEL,
                "message": "FAL_KEY is not configured in backend/.env",
            }
        return {
            "provider": "fal",
            "status": "READY",
            "model": FAL_IMAGE_MODEL,
            "message": "fal.ai FLUX Kontext image editing configured",
        }
    # NVIDIA hosted Flux — requires a key.
    if not NVIDIA_API_KEY:
        return {
            "provider": "nvidia",
            "status": "NOT_CONFIGURED",
            "model": NVIDIA_IMAGE_MODEL,
            "message": "NVIDIA_API_KEY is not configured in backend/.env",
        }
    return {
        "provider": "nvidia",
        "status": "READY",
        "model": NVIDIA_IMAGE_MODEL,
        "message": "NVIDIA API key configured",
    }
