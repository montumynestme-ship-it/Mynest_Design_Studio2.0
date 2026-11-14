"""DEV-ONLY diagnostic: does the CONFIGURED hosted NVIDIA image model accept an
ARBITRARY generated PNG (the real deterministic room render)?

NOT production, NOT a fallback. Sends the real base render both ways the docs allow
and records the exact provider response, then classifies the outcome. Never logs the
API key. Reads the image from a local file path given as argv[1].
"""

from __future__ import annotations

import base64
import sys
import time
from pathlib import Path

import httpx

from app.core.config import NVIDIA_API_BASE, NVIDIA_API_KEY, NVIDIA_IMAGE_MODEL

UNSUPPORTED = "NVIDIA_ARBITRARY_IMAGE_UNSUPPORTED"
SUCCESS = "NVIDIA_IMG2IMG_SUCCESS"
AUTH = "NVIDIA_AUTH_FAILURE"


def _summary(t: str, n: int = 240) -> str:
    return " ".join((t or "")[:n].split())


def run(img_path: str) -> None:
    endpoint = f"{NVIDIA_API_BASE.rstrip('/')}/{NVIDIA_IMAGE_MODEL}"
    raw = Path(img_path).read_bytes()
    b64 = base64.b64encode(raw).decode()
    mime = "jpeg" if raw[:2] == b"\xff\xd8" else "png"
    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    print(f"model={NVIDIA_IMAGE_MODEL} endpoint={endpoint}")
    print(f"img={img_path} bytes={len(raw)} mime={mime}")
    if not NVIDIA_API_KEY:
        print(f"result={AUTH} reason=missing key")
        return
    # Documented arbitrary-image format for self-hosted NIM: data:image/<mime>;base64,<data>
    body = {
        "prompt": "modern luxury living room, photorealistic, preserve layout",
        "mode": "canny",
        "image": f"data:image/{mime};base64,{b64}",
        "cfg_scale": 3.5,
        "steps": 10,
        "seed": 0,
    }
    t0 = time.monotonic()
    try:
        with httpx.Client(timeout=httpx.Timeout(90.0, connect=10.0)) as c:
            r = c.post(endpoint, json=body, headers=headers)
    except httpx.HTTPError as exc:
        print(f"result=NVIDIA_PROVIDER_ERROR transport={type(exc).__name__}: {exc}")
        return
    dur = round(time.monotonic() - t0, 2)
    st = r.status_code
    print(f"http_status={st} duration_s={dur} response={_summary(r.text)}")
    if st in (401, 403):
        print(f"result={AUTH}")
    elif st == 200:
        # Would only happen on a self-hosted NIM / arbitrary-image-capable endpoint.
        print(f"result={SUCCESS} output_bytes~={len(r.content)}")
    else:
        # 4xx/5xx on an arbitrary base64 image => hosted Preview API rejects it.
        print(f"result={UNSUPPORTED} (hosted Preview API accepts only example_id 0-3)")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "")
