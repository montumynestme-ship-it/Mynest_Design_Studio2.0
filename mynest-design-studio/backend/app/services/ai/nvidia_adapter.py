import base64
import secrets
from typing import Any

import httpx

from app.core.config import NVIDIA_API_KEY, NVIDIA_IMAGE_MODEL
from app.services.ai.base import AIProviderAdapter, GenerationRequest

# flux.1-dev wants each side a multiple of 32 within [768, 1344]; returns a JPEG.
_MIN_SIDE, _MAX_SIDE = 768, 1344


def _snap(value: int) -> int:
    return max(_MIN_SIDE, min(_MAX_SIDE, round(value / 32) * 32))


class NvidiaAdapter(AIProviderAdapter):
    """NVIDIA API-catalog image generation.

    Ready for a valid `nvapi-...` key in NVIDIA_API_KEY. Raises on auth/config
    failure so the generation service can fall back to the demo provider.
    """

    name = "nvidia"

    def __init__(self) -> None:
        self.model = NVIDIA_IMAGE_MODEL
        self.url = f"https://ai.api.nvidia.com/v1/genai/{NVIDIA_IMAGE_MODEL}"

    def generate(self, request: GenerationRequest) -> list[bytes]:
        if not NVIDIA_API_KEY:
            raise RuntimeError("NVIDIA_API_KEY is not configured")
        headers = {
            "Authorization": f"Bearer {NVIDIA_API_KEY}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        images: list[bytes] = []
        with httpx.Client(timeout=180.0) as client:
            for _ in range(request.count):
                response = client.post(
                    self.url,
                    headers=headers,
                    json={
                        "prompt": request.prompt,
                        "width": _snap(request.width),
                        "height": _snap(request.height),
                        "steps": 20,
                        "cfg_scale": 3.5,
                        "seed": secrets.randbelow(2**31),  # vary each design
                    },
                )
                response.raise_for_status()
                images.append(_decode_image(response.json()))
        return images


def _decode_image(data: dict[str, Any]) -> bytes:
    """Extract PNG bytes from an NVIDIA image response (schema varies by model)."""
    if isinstance(data.get("artifacts"), list) and data["artifacts"]:
        return base64.b64decode(data["artifacts"][0]["base64"])
    if isinstance(data.get("image"), str):
        return base64.b64decode(data["image"])
    if isinstance(data.get("b64_json"), str):
        return base64.b64decode(data["b64_json"])
    raise ValueError("Unrecognized NVIDIA image response schema")
