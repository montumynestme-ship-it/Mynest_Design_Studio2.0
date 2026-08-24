"""fal.ai flux ControlNet adapter — geometry-locked img2img (Phase C).

Sends the deterministic canny control map (walls + furniture) to fal's flux
ControlNet so the model repaints it photorealistically while tracing the exact
geometry. The control image is authoritative (CLAUDE.md RULE #1); the model only
adds materials, lighting, and styling.

NOTE: the account must hold a balance or fal returns 403 "User is locked. Reason:
TOP_UP". FalControlNetError carries fal's message through to the API layer.
"""

import base64

import httpx

from app.core.config import FAL_CONTROLNET_MODEL, FAL_KEY


class FalControlNetError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class FalControlNetAdapter:
    """Geometry-locked rendering via fal.ai flux ControlNet (canny)."""

    name = "fal"

    def __init__(self) -> None:
        self.model = FAL_CONTROLNET_MODEL
        self.url = f"https://fal.run/{FAL_CONTROLNET_MODEL}"

    def generate(self, control_png: bytes, prompt: str, width: int, height: int) -> bytes:
        """Return PNG bytes of the geometry-locked render."""
        if not FAL_KEY:
            raise FalControlNetError(500, "FAL_KEY is not configured")

        control_uri = "data:image/png;base64," + base64.b64encode(control_png).decode()
        headers = {"Authorization": f"Key {FAL_KEY}", "Content-Type": "application/json"}
        body = {
            "prompt": prompt,
            "image_url": control_uri,  # the canny control map
            "image_size": {"width": width, "height": height},
            "num_inference_steps": 28,
            "guidance_scale": 30.0,  # canny ControlNet wants high guidance
            "num_images": 1,
            "enable_safety_checker": False,
        }
        try:
            with httpx.Client(timeout=240.0) as client:
                response = client.post(self.url, headers=headers, json=body)
                if response.status_code != 200:
                    detail = _fal_error(response)
                    raise FalControlNetError(response.status_code, detail)
                data = response.json()
                image_url = data["images"][0]["url"]
                image = client.get(image_url)
                image.raise_for_status()
                return image.content
        except httpx.HTTPError as exc:
            raise FalControlNetError(502, f"fal.ai request failed: {exc}") from exc


def _fal_error(response: httpx.Response) -> str:
    try:
        data = response.json()
        if isinstance(data, dict) and "detail" in data:
            return str(data["detail"])
    except Exception:  # noqa: BLE001 — non-JSON error body
        pass
    return response.text[:300]
