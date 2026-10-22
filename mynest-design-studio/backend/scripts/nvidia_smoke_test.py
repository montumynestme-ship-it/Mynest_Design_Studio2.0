"""DEVELOPMENT-ONLY NVIDIA FLUX smoke test — NOT a production path, NOT a fallback.

Purpose
-------
Verify NVIDIA hosted ``black-forest-labs/flux.1-dev`` provider connectivity, auth and
model in BASE (text-to-image) mode with NO input image, isolated from the real
geometry-locked image-to-image AI Render pipeline. This exists ONLY to answer
"can this account reach the FLUX provider at all?" independently of the img2img
(ControlNet) path that the account currently 500s on.

Hard rules
----------
* This output MUST NEVER be fed into the room AI Render flow (it is a plain
  text-to-image image with no geometry lock).
* It does NOT import or modify the production adapter's generate path.
* It NEVER logs NVIDIA_API_KEY.
* One request, no indefinite retries.

Run:  python -m scripts.nvidia_smoke_test   (from the backend/ directory)
"""

from __future__ import annotations

import base64
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

# Read-only config (server-side). We do NOT import the adapter's generate() so this
# can never affect production behavior.
from app.core.config import NVIDIA_API_BASE, NVIDIA_API_KEY, NVIDIA_IMAGE_MODEL

# --- Smoke-test parameters (conservative, officially supported) ---------------
MODE = "base"  # text-to-image; NO input image
PROMPT = (
    "modern luxury interior room, architectural visualization, "
    "warm neutral materials, realistic daylight"
)
WIDTH = 1024   # an officially supported flux.1-dev side length
HEIGHT = 1024
STEPS = 8      # conservative
CFG_SCALE = 3.5
CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 60.0
OUT_DIR = Path(__file__).resolve().parent.parent / "dev_smoke_output"

# Result statuses (per goal)
SUCCESS = "NVIDIA_SMOKE_TEST_SUCCESS"
AUTH_FAILURE = "NVIDIA_AUTH_FAILURE"
VALIDATION_FAILURE = "NVIDIA_VALIDATION_FAILURE"
TIMEOUT = "NVIDIA_TIMEOUT"
PROVIDER_ERROR = "NVIDIA_PROVIDER_ERROR"


def _body_summary(text: str, limit: int = 300) -> str:
    """A short, safe one-line summary of the provider response body."""
    return " ".join((text or "")[:limit].split())


def _extract_image_b64(payload: dict) -> str | None:
    """Pull a base64 image out of an NVIDIA hosted-image response (artifacts[].base64
    or common variants). Mirrors the real contract WITHOUT importing the adapter."""
    arts = payload.get("artifacts") or payload.get("data") or []
    if isinstance(arts, list):
        for a in arts:
            if isinstance(a, dict):
                b64 = a.get("base64") or a.get("b64_json") or a.get("image")
                if isinstance(b64, str) and b64:
                    return b64
    for key in ("image", "b64_json", "image_base64"):
        v = payload.get(key)
        if isinstance(v, str) and v:
            return v
    return None


def run() -> str:
    endpoint = f"{NVIDIA_API_BASE.rstrip('/')}/{NVIDIA_IMAGE_MODEL}"
    report: dict[str, object] = {
        "model": NVIDIA_IMAGE_MODEL,
        "endpoint": endpoint,
        "mode": MODE,
        "width": WIDTH,
        "height": HEIGHT,
        "steps": STEPS,
        "cfg_scale": CFG_SCALE,
        "api_key_present": bool(NVIDIA_API_KEY),
    }

    def emit(status: str, **extra: object) -> str:
        report.update(extra)
        report["result"] = status
        print("=== NVIDIA FLUX smoke test (DEV-ONLY, base/text-to-image) ===")
        for k in (
            "result", "model", "endpoint", "mode", "width", "height", "steps",
            "cfg_scale", "api_key_present", "http_status", "request_duration_s",
            "response_summary", "output_bytes", "image_dimensions", "image_format",
            "saved_to",
        ):
            if k in report:
                print(f"  {k}: {report[k]}")
        return status

    # 1) Key must exist server-side (value never printed).
    if not NVIDIA_API_KEY:
        return emit(AUTH_FAILURE, response_summary="NVIDIA_API_KEY missing in backend config/.env")

    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    # BASE mode = text-to-image: explicit mode="base", NO `image`/example_id/
    # ControlNet field. This is the EXACT production request contract.
    body = {
        "prompt": PROMPT,
        "mode": MODE,  # "base"
        "cfg_scale": CFG_SCALE,
        "steps": STEPS,
        "seed": 0,
        "width": WIDTH,
        "height": HEIGHT,
    }

    t0 = time.monotonic()
    try:
        with httpx.Client(
            timeout=httpx.Timeout(READ_TIMEOUT, connect=CONNECT_TIMEOUT)
        ) as client:
            resp = client.post(endpoint, json=body, headers=headers)
    except httpx.TimeoutException as exc:
        return emit(
            TIMEOUT,
            request_duration_s=round(time.monotonic() - t0, 2),
            response_summary=f"timeout: {type(exc).__name__}",
        )
    except httpx.HTTPError as exc:
        return emit(
            PROVIDER_ERROR,
            request_duration_s=round(time.monotonic() - t0, 2),
            response_summary=f"transport error: {type(exc).__name__}: {exc}",
        )

    dur = round(time.monotonic() - t0, 2)
    status = resp.status_code
    report["http_status"] = status
    report["request_duration_s"] = dur

    if status in (401, 403):
        return emit(AUTH_FAILURE, response_summary=_body_summary(resp.text))
    if status in (400, 422):
        return emit(VALIDATION_FAILURE, response_summary=_body_summary(resp.text))
    if status != 200:
        return emit(PROVIDER_ERROR, response_summary=_body_summary(resp.text))

    # 200 — parse and save.
    try:
        payload = resp.json()
    except ValueError:
        return emit(PROVIDER_ERROR, response_summary="200 but body was not JSON")
    b64 = _extract_image_b64(payload)
    if not b64:
        return emit(
            PROVIDER_ERROR,
            response_summary=f"200 but no image in response; keys={list(payload)[:8]}",
        )
    try:
        img = base64.b64decode(b64)
    except (ValueError, TypeError):
        return emit(PROVIDER_ERROR, response_summary="200 but image base64 could not be decoded")
    if not img:
        return emit(PROVIDER_ERROR, response_summary="200 but decoded image was empty")

    # Verify the decoded bytes are a real, non-empty raster with valid dimensions.
    try:
        from io import BytesIO

        from PIL import Image

        with Image.open(BytesIO(img)) as im:
            im.verify()
        with Image.open(BytesIO(img)) as im2:
            iw, ih = im2.size
            img_format = im2.format
        if iw <= 0 or ih <= 0:
            return emit(PROVIDER_ERROR, response_summary=f"decoded image has invalid dims {iw}x{ih}")
        report["image_dimensions"] = f"{iw}x{ih}"
        report["image_format"] = img_format
    except Exception as exc:  # noqa: BLE001
        return emit(PROVIDER_ERROR, response_summary=f"decoded bytes are not a valid image: {exc}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    # NVIDIA hosted FLUX returns JPEG bytes in artifacts[].base64 — use the real
    # extension so the saved file is honest about its content.
    ext = "jpg" if img[:2] == b"\xff\xd8" else ("png" if img[:8].startswith(b"\x89PNG") else "img")
    out_path = OUT_DIR / f"nvidia_smoke_{MODE}_{ts}.{ext}"
    out_path.write_bytes(img)
    return emit(
        SUCCESS,
        response_summary=f"200 OK; artifacts image decoded ({len(img)} bytes)",
        output_bytes=len(img),
        saved_to=str(out_path),
    )


if __name__ == "__main__":
    result = run()
    # Non-zero exit on any failure so CI/dev can detect it, but never leak the key.
    sys.exit(0 if result == SUCCESS else 1)
