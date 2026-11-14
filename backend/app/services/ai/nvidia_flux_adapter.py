"""NVIDIA-hosted Flux image-generation adapter — the ONLY AI image provider.

Calls the NVIDIA hosted image API (build.nvidia.com / ai.api.nvidia.com) with
`Authorization: Bearer <NVIDIA_API_KEY>`. There is NO pollinations, BFL, Gemini,
or Three.js fallback — a failure surfaces a real error.

Image-to-image: the hosted flux.1-dev endpoint is TEXT-TO-IMAGE and rejects a
user input image. When NVIDIA_IMAGE_MODEL points at an image-capable NVIDIA
model, set NVIDIA_SUPPORTS_IMG2IMG=true and the deterministic base render is sent
as the input image. By default this is text-to-image driven by the geometry /
inventory prompt (no pretend img2img).

Keys are server-side only and never logged or returned.
"""

import base64
import logging
import os
import random
import re
import time
from datetime import datetime, timezone
from io import BytesIO
from typing import Any
from urllib.parse import urlparse

import httpx
from PIL import Image

from app.core.config import (
    AI_TIMEOUT_SECONDS,
    NVIDIA_API_BASE,
    NVIDIA_API_KEY,
    NVIDIA_ARBITRARY_IMAGE_SUPPORTED,
    NVIDIA_IMAGE_MODEL,
    NVIDIA_IMG2IMG_MODE,
    NVIDIA_MAX_ATTEMPTS,
    NVIDIA_NIM_INFER_PATH,
    NVIDIA_SUPPORTS_IMG2IMG,
)
from app.services.ai.base import AIProviderAdapter, AIProviderError, GenerationRequest

logger = logging.getLogger("app.services.ai.nvidia_flux")

# ── Model capability model (data, NOT env flags) ──────────────────────────────
# What each NVIDIA image model can ACTUALLY do. An env flag may DISABLE a
# capability but can NEVER fabricate one the model lacks (spec tasks 5, 6, 8):
#   TEXT_TO_IMAGE           — prompt -> image (all flux image models).
#   IMAGE_GUIDED_GENERATION — ControlNet on an input image (canny/depth): keeps
#                             the input's structure while restyling.
#   IMAGE_EDITING           — instruction-guided edit of an input image (kontext).
#   ARBITRARY_IMAGE_INPUT   — accepts a real, caller-supplied image (required for
#                             our geometry-lock base render). flux.1-dev does NOT.
TEXT_TO_IMAGE = "TEXT_TO_IMAGE"
IMAGE_GUIDED_GENERATION = "IMAGE_GUIDED_GENERATION"
IMAGE_EDITING = "IMAGE_EDITING"
ARBITRARY_IMAGE_INPUT = "ARBITRARY_IMAGE_INPUT"

_MODEL_CAPABILITIES: dict[str, set[str]] = {
    "black-forest-labs/flux.1-dev": {TEXT_TO_IMAGE},
    "black-forest-labs/flux.1-schnell": {TEXT_TO_IMAGE},
    "black-forest-labs/flux.1-canny-dev": {
        TEXT_TO_IMAGE, IMAGE_GUIDED_GENERATION, ARBITRARY_IMAGE_INPUT,
    },
    "black-forest-labs/flux.1-depth-dev": {
        TEXT_TO_IMAGE, IMAGE_GUIDED_GENERATION, ARBITRARY_IMAGE_INPUT,
    },
    "black-forest-labs/flux.1-kontext-dev": {
        TEXT_TO_IMAGE, IMAGE_EDITING, ARBITRARY_IMAGE_INPUT,
    },
}

# NVIDIA-hosted image API hosts. Anything else in NVIDIA_API_BASE is treated as a
# self-hosted NIM, which uses a fixed inference route (NVIDIA_NIM_INFER_PATH),
# NOT the {base}/{model} form the hosted API uses.
_HOSTED_HOST_SUFFIX = ".api.nvidia.com"


def model_capabilities(model: str) -> set[str] | None:
    """Known capabilities for a model, or None when the model name is unknown
    (e.g. a custom self-hosted NIM) — capability then cannot be detected from the
    name and the operator's NVIDIA_ARBITRARY_IMAGE_SUPPORTED assertion governs."""
    return _MODEL_CAPABILITIES.get((model or "").strip())


def model_supports_arbitrary_image(model: str) -> bool | None:
    """True / False for a known model; None when the model is unknown."""
    caps = model_capabilities(model)
    if caps is None:
        return None
    return ARBITRARY_IMAGE_INPUT in caps


def deployment_mode(base: str) -> str:
    """"hosted" for an ai.api.nvidia.com endpoint, else "self_hosted_nim"."""
    host = (urlparse(base).hostname or "").lower()
    return "hosted" if host.endswith(_HOSTED_HOST_SUFFIX) else "self_hosted_nim"


def resolve_endpoint(base: str, model: str) -> str:
    """Mode-aware endpoint. Hosted: {base}/{model}. Self-hosted NIM:
    {base}{NVIDIA_NIM_INFER_PATH} — the model is selected by the NIM itself and is
    NOT appended to the path."""
    base = (base or "").rstrip("/")
    if deployment_mode(base) == "hosted":
        return f"{base}/{model}"
    path = NVIDIA_NIM_INFER_PATH if NVIDIA_NIM_INFER_PATH.startswith("/") else f"/{NVIDIA_NIM_INFER_PATH}"
    return f"{base}{path}"


def effective_arbitrary_image_input(
    model: str, operator_flag: bool, deployment: str | None = None
) -> bool:
    """The GENUINE arbitrary-image-input capability.

    Requires ALL of: the operator opts in (flag) AND the model supports it AND the
    DEPLOYMENT accepts an arbitrary uploaded image. VERIFIED LIVE: the HOSTED
    ai.api.nvidia.com image endpoints accept ONLY predefined example images
    (image=example_id,0-3) and reject an arbitrary base64 OR uploaded asset with
    HTTP 422 ("Expected: example_id, got: base64|asset_id") — for flux.1-kontext-dev
    exactly as for flux.1-dev. So arbitrary image input is genuinely available ONLY
    on a self-hosted NIM. A known-incapable model (flux.1-dev) is False even when the
    flag is True; an unknown model defers to the operator flag (self-hosted only)."""
    if deployment == "hosted":
        return False  # hosted image endpoints are example_id-only (verified 422)
    model_arb = model_supports_arbitrary_image(model)
    if model_arb is None:
        return operator_flag  # custom NIM — undetectable from name, trust operator
    return operator_flag and model_arb


def effective_config_summary() -> dict[str, object]:
    """Single source of truth for startup logs and /api/ai-diagnostics. Reports
    the EFFECTIVE (capability-checked) state, never merely the raw env flags, and
    never the API key value."""
    base = (NVIDIA_API_BASE or "").rstrip("/")
    caps = model_capabilities(NVIDIA_IMAGE_MODEL)
    dep = deployment_mode(base)
    arb_eff = effective_arbitrary_image_input(
        NVIDIA_IMAGE_MODEL, NVIDIA_ARBITRARY_IMAGE_SUPPORTED, dep
    )
    return {
        "provider": "nvidia",
        "model": NVIDIA_IMAGE_MODEL,
        "endpoint": resolve_endpoint(base, NVIDIA_IMAGE_MODEL),
        "deployment_mode": dep,
        "img2img_requested": NVIDIA_SUPPORTS_IMG2IMG,
        "arbitrary_image_requested": NVIDIA_ARBITRARY_IMAGE_SUPPORTED,
        "image_input_supported": arb_eff,          # GENUINE capability, not the flag
        "conditioning_mode": NVIDIA_IMG2IMG_MODE,
        "model_declared_capabilities": sorted(caps) if caps is not None else None,
        "api_key_present": bool(NVIDIA_API_KEY),
    }

# NVIDIA hosted Flux accepts only these side lengths.
_VALID_SIDES = (768, 832, 896, 960, 1024, 1088, 1152)
_RETRYABLE = {429, 500, 502, 503, 504}
# ControlNet modes (image + mode + preprocess_image → server builds an edge/depth
# control map). "base" is text-to-image (no control image). "edit" is instruction
# image-editing (flux.1-kontext-dev): the supplied image is edited directly per the
# prompt, with NO canny/depth preprocessing.
_CONTROL_MODES = ("canny", "depth")
_EDIT_MODE = "edit"

# NVIDIA NIM Visual Generative AI specification:
# Image conditioning expects an inline base64 data URI: `data:image/png;base64,<base64>`.
# The hosted preview playground on ai.api.nvidia.com restricts image to static demo examples
# (example_id 0..3) and rejects arbitrary user images with HTTP 422.
# Using fabricated formats such as `data:image/png;example_id,<assetId>` is invalid and caused
# NVIDIA's backend router to hang and trigger HTTP 504 read timeouts.
_NVCF_ASSETS_URL = "https://api.nvcf.nvidia.com/v2/nvcf/assets"
_ASSET_DESC = "mynest-deterministic-base-render"

# Geometry-lock instruction (spec §5). Prepended to the prompt; leads the
# image-to-image request. With ControlNet the base render's structure is locked
# by the control map, so this text reinforces "restyle only, invent nothing".
_IMG2IMG_PREAMBLE = (
    "Preserve the exact architectural geometry and layout of the input image.\n"
    "The input image is the authoritative 3D scene. DO NOT move, remove, add, resize, "
    "rotate, relocate, or redesign any architectural element.\n\n"
    "STRICT GEOMETRY LOCK:\n"
    "- Preserve every door exactly at its existing position, wall, width, height, "
    "orientation, and swing direction.\n"
    "- Preserve every window exactly at its existing position, wall, width, height, and "
    "orientation.\n"
    "- Preserve all walls, room boundaries, openings, furniture positions, furniture "
    "sizes, and furniture rotations.\n"
    "- Doors and windows must remain on the same walls as in the input image.\n"
    "- Do not invent additional doors or windows.\n"
    "- Do not remove any existing doors or windows.\n"
    "- Do not mirror, flip, or swap room geometry.\n"
    "- Do not change camera framing or architectural proportions.\n\n"
    "Only enhance the visual appearance:\n"
    "- materials\n"
    "- wall colors\n"
    "- textures\n"
    "- furniture materials\n"
    "- lighting\n"
    "- ceiling treatment\n"
    "- decorative styling\n"
    "- realistic shadows and reflections\n\n"
    "The output must remain pixel-level and spatially consistent with the input "
    "geometry. Treat the input image as a structural constraint, not merely a visual "
    "reference.\n"
    "If a door or window is visible in the input, it MUST remain visible in the "
    "corresponding location in the output.\n"
    "GEOMETRY HAS HIGHER PRIORITY THAN STYLE.\n"
    "STYLE CHANGES MUST NEVER MODIFY ARCHITECTURAL GEOMETRY."
)


def _snap(value: int) -> int:
    """Snap a dimension to the nearest NVIDIA-supported side length."""
    return min(_VALID_SIDES, key=lambda s: abs(s - value))


# A long unbroken base64/token run — image bytes in a success body, or anything
# that could carry opaque data. Redacted from every log line.
_B64_RUN = re.compile(r"[A-Za-z0-9+/=_-]{40,}")


def _safe_body_summary(text: str, limit: int = 200) -> str:
    """One-line, log-safe summary of a provider response body: collapse whitespace,
    redact any long base64/token run (image data, credentials), then truncate.
    Guarantees no image bytes and no key material ever reach the logs."""
    collapsed = " ".join((text or "").split())
    redacted = _B64_RUN.sub("<redacted:base64>", collapsed)
    return redacted[:limit]


# Response headers NVIDIA / NVCF use to carry a request/correlation id (checked in
# order). Surfaced in errors so a provider-side failure is actionable in a ticket.
_REQID_HEADERS = (
    "nvcf-reqid", "x-request-id", "x-nvcf-request-id", "nv-request-id",
    "x-nvrequestid", "request-id",
)


def _request_id(headers: Any) -> str | None:
    """Extract a provider request/correlation id from response headers (never a key).

    Case-insensitive: httpx.Headers already is, and a plain-dict header map works too.
    """
    try:
        lowered = {str(k).lower(): v for k, v in dict(headers).items()}
    except Exception:  # noqa: BLE001
        lowered = {}
    for name in _REQID_HEADERS:
        val = lowered.get(name)
        if val:
            return str(val)
    return None


def _to_png(data: bytes) -> bytes:
    """Normalize image bytes (JPEG/PNG) to a valid, non-empty PNG."""
    image = Image.open(BytesIO(data)).convert("RGB")
    w, h = image.size
    if w <= 0 or h <= 0:
        raise ValueError(f"Invalid image dimensions: {w}x{h}")
    buf = BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _prep_control_png(data: bytes, width: int, height: int) -> bytes:
    """Resize the deterministic base render to a NVIDIA-supported size, as PNG
    bytes ready to upload as an NVCF asset."""
    image = Image.open(BytesIO(data)).convert("RGB").resize((width, height))
    buf = BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _clean_prompt(prompt: str) -> str:
    """Condense the room prompt into the visual description sent to the model,
    dropping the verbose constraint boilerplate and appending style + negatives."""
    for marker in (
        "================================================================================",
        "AUTHORITATIVE GEOMETRY & INVENTORY CONSTRAINT",
        "MANDATORY NEGATIVE CONSTRAINTS",
        "CRITICAL LAYOUT HIERARCHY",
    ):
        if marker in prompt:
            prompt = prompt.split(marker)[0]

    lines = [ln.strip() for ln in prompt.split("\n") if ln.strip()]
    visual_parts: list[str] = []
    for line in lines:
        if line.startswith("This is STRICTLY"):
            continue
        visual_parts.append(line.replace("—", "-"))

    combined = " ".join(visual_parts).strip()
    for old in (
        "24mm lens",
        "30mm architectural lens",
        "32mm architectural lens",
        "30mm architectural wide-angle lens",
        "32mm architectural wide-angle lens",
    ):
        combined = combined.replace(
            old, "35mm lens, natural perspective, straight vertical walls, no fisheye"
        )
    if "35mm lens" not in combined:
        combined = "35mm lens, natural perspective, straight vertical walls, no fisheye. " + combined

    luxury_suffix = (
        " Modern luxury interior, Premium Modern Contemporary residential interior architecture, "
        "shot on a natural 35mm lens with straight vertical walls and no fisheye distortion, "
        "warm 3000K concealed architectural cove lighting, refined walnut and natural stone finishes, "
        "bouclé and linen upholstery, soft natural daylight, realistic shadows and reflections, "
        "architectural photography, 8k photorealistic interior render, Architectural Digest photography."
    )
    negative_suffix = (
        " Avoid: added/removed/moved furniture, kitchen island, bar stools, extra chairs or "
        "tables, merged sofas, moved wardrobes, re-oriented bed, moved walls/windows/doors, "
        "invented partitions, changed proportions or camera, fisheye lens, dark unlit room, "
        "CGI look, plastic surface, generic showroom."
    )
    reserve = len(luxury_suffix) + len(negative_suffix) + 5
    max_body_len = 1500 - reserve
    if len(combined) > max_body_len:
        combined = combined[:max_body_len].rstrip() + "..."
    if not combined.endswith("."):
        combined += "."
    if "Modern luxury interior" not in combined:
        combined += luxury_suffix
    combined += negative_suffix
    return combined


def _extract_image(payload: dict[str, Any]) -> bytes | None:
    """Pull an image out of an NVIDIA hosted-image response.

    Handles the artifacts[].base64 (JPEG b64) shape and a few common variants
    (image/b64_json fields, or an artifacts[].url to download by the caller)."""
    arts = payload.get("artifacts") or payload.get("data") or []
    if isinstance(arts, list):
        for a in arts:
            if not isinstance(a, dict):
                continue
            b64 = a.get("base64") or a.get("b64_json") or a.get("image")
            if b64:
                try:
                    return base64.b64decode(b64)
                except Exception:  # noqa: BLE001
                    continue
    for key in ("image", "b64_json", "image_base64"):
        val = payload.get(key)
        if isinstance(val, str) and val:
            try:
                return base64.b64decode(val)
            except Exception:  # noqa: BLE001
                pass
    return None


def _image_url(payload: dict[str, Any]) -> str | None:
    arts = payload.get("artifacts") or []
    if isinstance(arts, list):
        for a in arts:
            if isinstance(a, dict) and isinstance(a.get("url"), str):
                return a["url"]
    return payload.get("url") if isinstance(payload.get("url"), str) else None


class NvidiaFluxAdapter(AIProviderAdapter):
    """NVIDIA-hosted Flux image generator (the only provider)."""

    name = "nvidia"
    model = NVIDIA_IMAGE_MODEL
    supports_seed = True

    def __init__(self, timeout: float = AI_TIMEOUT_SECONDS) -> None:
        self.timeout = max(timeout, 45.0)
        self.api_key = NVIDIA_API_KEY
        self.model = NVIDIA_IMAGE_MODEL
        self.base = NVIDIA_API_BASE.rstrip("/")
        # Image-to-image sends the deterministic base render as a ControlNet/edit
        # input so the output preserves its geometry. Off by default (text-to-image).
        self.mode = NVIDIA_IMG2IMG_MODE if NVIDIA_SUPPORTS_IMG2IMG else "base"
        self.supports_image_reference = NVIDIA_SUPPORTS_IMG2IMG
        self.supports_control_image = NVIDIA_SUPPORTS_IMG2IMG
        # Deployment + GENUINE (capability-checked) image-input support. These are
        # derived from the model + endpoint, NOT merely from the env flags, so
        # diagnostics and the request gate never over-claim (spec tasks 5, 6).
        self.deployment = deployment_mode(self.base)
        self.model_caps = model_capabilities(self.model)  # set | None (unknown NIM)
        self.arbitrary_image_effective = effective_arbitrary_image_input(
            self.model, NVIDIA_ARBITRARY_IMAGE_SUPPORTED, self.deployment
        )

    def _endpoint(self) -> str:
        return resolve_endpoint(self.base, self.model)

    def _upload_asset(self, png: bytes) -> str:
        """Upload the base render via the NVCF asset API and return its assetId.

        Hosted image models cannot take an inline image; the base render must be an
        uploaded asset (create -> presigned PUT), then referenced by id. Raises
        AIProviderError with a clear reason on any failure (never a fake success).
        """
        auth = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                created = client.post(
                    _NVCF_ASSETS_URL,
                    headers={**auth, "Content-Type": "application/json"},
                    json={"contentType": "image/png", "description": _ASSET_DESC},
                )
                if created.status_code >= 300:
                    raise AIProviderError(
                        "nvidia",
                        f"NVCF asset create failed (HTTP {created.status_code}): {created.text[:160]}",
                        created.status_code, self.model,
                    )
                info = created.json()
                asset_id, upload_url = info["assetId"], info["uploadUrl"]
                put = client.put(
                    upload_url,
                    headers={
                        "Content-Type": "image/png",
                        "x-amz-meta-nvcf-asset-description": _ASSET_DESC,
                    },
                    content=png,
                )
                if put.status_code >= 300:
                    raise AIProviderError(
                        "nvidia",
                        f"NVCF asset upload failed (HTTP {put.status_code})",
                        put.status_code, self.model,
                    )
                return str(asset_id)
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            raise AIProviderError("nvidia", f"NVCF asset upload connection failed: {exc}", 504, self.model) from exc

    @staticmethod
    def _log_diagnostics(
        *,
        room_id: str | None,
        room_label: str,
        model: str,
        endpoint: str,
        prompt_length: int,
        base_png_dimensions: str | None,
        base_png_byte_size: int,
        asset_upload_started: bool,
        asset_upload_success: bool,
        asset_id_present: bool,
        request_started_at: str,
        request_timeout_seconds: float,
        mode: str,
        steps: Any,
        width: int,
        height: int,
        cfg_scale: Any,
        http_status: int | None,
        body_summary: str,
        request_duration: float,
        retry_number: int,
    ) -> None:
        """Safe structured diagnostics logging (never logs keys, credentials, or image bytes)."""
        logger.info(
            "[NVIDIA DIAGNOSTICS]\n"
            "  room_id: %s\n"
            "  room_label: %s\n"
            "  model: %s\n"
            "  endpoint: %s\n"
            "  prompt_length: %d\n"
            "  base_png_dimensions: %s\n"
            "  base_png_byte_size: %d\n"
            "  asset_upload_started: %s\n"
            "  asset_upload_success: %s\n"
            "  asset_id_present: %s\n"
            "  request_started_at: %s\n"
            "  request_timeout_seconds: %.1f\n"
            "  mode: %s\n"
            "  steps: %s\n"
            "  width: %d\n"
            "  height: %d\n"
            "  cfg_scale: %s\n"
            "  HTTP status: %s\n"
            "  response body summary: %s\n"
            "  request duration: %.3fs\n"
            "  retry number: %d",
            room_id,
            room_label,
            model,
            endpoint,
            prompt_length,
            base_png_dimensions,
            base_png_byte_size,
            asset_upload_started,
            asset_upload_success,
            asset_id_present,
            request_started_at,
            request_timeout_seconds,
            mode,
            steps,
            width,
            height,
            cfg_scale,
            http_status,
            body_summary,
            request_duration,
            retry_number,
        )

    def _log_failure(
        self,
        *,
        room_label: str,
        status: int,
        attempt: int,
        max_attempts: int,
        generation_id: str | None,
        control_image: bool,
        elapsed: float | None,
        request_id: str | None,
        error: str,
    ) -> None:
        """Concise, sanitized per-failure log (no keys/headers/payloads). Gives ops
        exactly what's needed to triage: provider, model, room, HTTP status, retry
        position, generation + provider request ids, whether a control image was
        supplied, elapsed time, and the redacted upstream error."""
        logger.warning(
            "[AI][NVIDIA] generation failed provider=nvidia model=%s room=%s "
            "status=%s attempt=%d/%d generation_id=%s request_id=%s "
            "control_image=%s elapsed=%s error=%s",
            self.model, room_label, status, attempt, max_attempts,
            generation_id, request_id, control_image,
            f"{elapsed:.2f}s" if elapsed is not None else "n/a",
            _safe_body_summary(error),
        )

    def _build_body(
        self,
        request: GenerationRequest,
        width: int,
        height: int,
        control_b64: str | None = None,
        asset_id: str | None = None,
    ) -> dict[str, Any]:
        img2img = (control_b64 is not None) or (asset_id is not None)
        prompt = (_IMG2IMG_PREAMBLE + "\n\n" + request.prompt) if img2img else request.prompt
        body: dict[str, Any] = {
            "prompt": _clean_prompt(prompt),
            "cfg_scale": 3.5,
            "steps": 40 if img2img else 30,
            "seed": request.seed if request.seed is not None else 0,
        }
        if img2img:
            # NVIDIA official NIM image input contract:
            # For Canny/Depth control, image is passed as an inline base64 data URI:
            #   data:image/png;base64,<base64>
            # (If an NVCF asset reference is supported, it uses data:image/png;asset_id,<asset_id>).
            # The control image dictates the output aspect, so width/height are omitted.
            # Prefer an uploaded NVCF asset reference when present: the HOSTED image
            # endpoints reject an inline arbitrary base64 image (HTTP 422 "Expected:
            # example_id, got: base64") and require the image to be uploaded as an
            # asset (NVIDIA_UPLOAD_NVCF_ASSETS) and referenced by id. Inline base64 is
            # the fallback for endpoints that DO accept it (e.g. a self-hosted NIM).
            if asset_id is not None:
                body["image"] = f"data:image/png;asset_id,{asset_id}"
            elif control_b64 is not None:
                body["image"] = f"data:image/png;base64,{control_b64}"

            if self.mode in _CONTROL_MODES:
                # ControlNet (canny/depth): the server preprocesses the supplied
                # image into an edge/depth control map that constrains the output.
                body["mode"] = self.mode
                body["preprocess_image"] = True
            elif self.mode == _EDIT_MODE:
                # Image editing (flux.1-kontext-dev): the supplied image is edited
                # directly per the prompt. Verified against the live hosted endpoint:
                # kontext REJECTS a `mode` field (HTTP 422 extra_forbidden "mode") and
                # does no canny/depth preprocessing — so send ONLY the image (set
                # above) plus the prompt + sampling params already in `body`.
                pass
        else:
            # Text-to-image: the model sizes the output.
            body["width"] = width
            body["height"] = height
            body["mode"] = "base"
        return body

    def generate(self, request: GenerationRequest) -> list[bytes]:
        if not self.api_key:
            raise AIProviderError(
                "nvidia", "NVIDIA_API_KEY is not configured in backend/.env", 401, self.model
            )
        width, height = _snap(request.width), _snap(request.height)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        room_id = getattr(request, "room_id", None) or f"room_{getattr(request, 'room_label', None) or 'unknown'}"
        room_label = getattr(request, "room_label", None) or "unknown"
        endpoint = self._endpoint()

        # Safe, per-generation config diagnostic. Reports ONLY the flag/mode state —
        # NEVER the API key, Authorization header, or any base64 image data. img2img
        # actually engages only when supports_control_image (SUPPORTS) AND a control
        # image is present AND arbitrary-image is enabled; otherwise conditioning is
        # "base" (text-to-image).
        control_image_present = request.control_image is not None
        # Compute the GENUINE image-input capability LIVE (model + current flag) so
        # the diagnostic always matches the request gate below, never a stale snapshot.
        arbitrary_effective = effective_arbitrary_image_input(
            self.model, NVIDIA_ARBITRARY_IMAGE_SUPPORTED, self.deployment
        )
        img2img_active = (
            self.supports_control_image
            and control_image_present
            and arbitrary_effective
        )
        logger.info(
            "AI_RENDER_CONFIG model=%s endpoint=%s deployment=%s img2img_enabled=%s "
            "arbitrary_image_requested=%s image_input_supported=%s "
            "control_image_present=%s conditioning_mode=%s",
            self.model,
            endpoint,
            self.deployment,
            self.supports_control_image,
            NVIDIA_ARBITRARY_IMAGE_SUPPORTED,
            arbitrary_effective,              # GENUINE capability, not the raw flag
            control_image_present,
            (self.mode if img2img_active else "base"),
        )

        base_png_dimensions: str | None = None
        base_png_byte_size = 0
        asset_upload_started = False
        asset_upload_success = False
        asset_id_present = False
        asset_id: str | None = None
        control_b64: str | None = None

        if self.supports_control_image and request.control_image is not None:
            # HARD, HONEST GATE (verified against NVIDIA's official OpenAPI contract
            # + a live probe with the real room render): the hosted build.nvidia.com
            # Preview API (flux.1-dev) accepts ONLY predefined example images
            # (`image: data:image/png;example_id,{0-3}`) and rejects a real base64
            # render with HTTP 422 "Expected: example_id, got: base64". There is NO
            # arbitrary-image mechanism on that hosted endpoint. Rather than fire a
            # doomed request and surface a misleading 422/500, refuse up front with a
            # clear production status. Arbitrary images require a SELF-HOSTED
            # flux.1-dev/canny/depth NIM (accepts data:image/<mime>;base64,<data> at
            # POST /v1/infer); set NVIDIA_ARBITRARY_IMAGE_SUPPORTED=true (with
            # NVIDIA_API_BASE pointing at that NIM) to enable the real img2img path.
            # Gate 1 — operator opt-in. Without the flag, never send an arbitrary
            # image (the hosted Preview API rejects it; this refusal is explicit,
            # never a silent doomed request).
            if not NVIDIA_ARBITRARY_IMAGE_SUPPORTED:
                raise AIProviderError(
                    "nvidia",
                    "NVIDIA_ARBITRARY_IMAGE_UNSUPPORTED: the configured hosted NVIDIA "
                    f"endpoint ({endpoint}) for model '{self.model}' accepts only "
                    "predefined example images (image=data:image/png;example_id,0-3) "
                    "and rejects an arbitrary uploaded PNG (HTTP 422 'Expected: "
                    "example_id, got: base64'). To render the real deterministic room "
                    "base image, deploy a self-hosted flux.1-dev / flux.1-canny-dev / "
                    "flux.1-depth-dev NIM (POST /v1/infer, image=data:image/<mime>;"
                    "base64,<data>) and set NVIDIA_ARBITRARY_IMAGE_SUPPORTED=true with "
                    "NVIDIA_API_BASE pointing at it.",
                    422,
                    self.model,
                )
            # Gate 2 — GENUINE model capability (spec tasks 5, 8). The flag alone
            # cannot make an incapable model do image-guided generation. A KNOWN
            # text-to-image model (e.g. flux.1-dev) is refused up front with a clear
            # capability error naming the models that CAN do it — never a doomed
            # request and never a misleading fake image. An UNKNOWN model (custom
            # NIM) can't be judged by name, so it proceeds on the operator's flag.
            if model_supports_arbitrary_image(self.model) is False:
                raise AIProviderError(
                    "nvidia",
                    f"NVIDIA_MODEL_CAPABILITY_MISSING: model '{self.model}' is "
                    f"{sorted(self.model_caps or [])} and does NOT support "
                    "ARBITRARY_IMAGE_INPUT / image-guided generation, so it cannot "
                    "preserve the deterministic base-render geometry. Geometry-locked "
                    "(image-guided) rendering requires a ControlNet model "
                    "(black-forest-labs/flux.1-canny-dev or flux.1-depth-dev) or an "
                    "image-edit model (black-forest-labs/flux.1-kontext-dev). Set "
                    "NVIDIA_IMAGE_MODEL to one of these on your self-hosted NIM and "
                    "keep NVIDIA_SUPPORTS_IMG2IMG=true, "
                    "NVIDIA_ARBITRARY_IMAGE_SUPPORTED=true.",
                    422,
                    self.model,
                    endpoint=endpoint,
                )
            # Gate 3 — DEPLOYMENT capability (verified live). The hosted
            # ai.api.nvidia.com image endpoints accept ONLY predefined example images
            # and reject an arbitrary base64 OR uploaded-asset image with HTTP 422
            # ("Expected: example_id, got: base64|asset_id") — proven for
            # flux.1-kontext-dev and flux.1-dev alike. So even a capable model cannot
            # take the deterministic base render on the HOSTED API. Refuse up front
            # with a precise message (no doomed request, no misleading image); real
            # arbitrary-image editing/conditioning requires a self-hosted NIM.
            if self.deployment == "hosted":
                raise AIProviderError(
                    "nvidia",
                    "NVIDIA_HOSTED_IMAGE_INPUT_UNSUPPORTED: the hosted endpoint "
                    f"({endpoint}) accepts ONLY predefined example images "
                    "(image=example_id,0-3) and rejects an arbitrary uploaded image "
                    "(verified HTTP 422 'Expected: example_id, got: base64/asset_id'), "
                    f"even for an image-capable model like '{self.model}'. Hosted "
                    "NVIDIA cannot edit/condition on the deterministic base render. "
                    "Arbitrary-image editing requires a SELF-HOSTED NIM "
                    "(black-forest-labs/flux.1-kontext-dev for editing, or "
                    "flux.1-canny-dev/flux.1-depth-dev for ControlNet), which needs an "
                    "NVIDIA GPU host. Text-to-image on the hosted API still works "
                    "(NVIDIA_SUPPORTS_IMG2IMG=false).",
                    422,
                    self.model,
                    endpoint=endpoint,
                )
            try:
                raw_img = Image.open(BytesIO(request.control_image))
                base_png_dimensions = f"{raw_img.width}x{raw_img.height}"
            except Exception:
                base_png_dimensions = f"{width}x{height}"
            base_png_byte_size = len(request.control_image)

            png = _prep_control_png(request.control_image, width, height)
            if os.getenv("NVIDIA_UPLOAD_NVCF_ASSETS", "false").lower() in ("1", "true", "yes"):
                asset_upload_started = True
                try:
                    asset_id = self._upload_asset(png)
                    asset_upload_success = True
                    asset_id_present = True
                    headers["NVCF-INPUT-ASSET-REFERENCES"] = asset_id
                except Exception as exc:
                    asset_upload_success = False
                    logger.warning("[NVIDIA] NVCF asset upload failed: %s", exc)
            control_b64 = base64.b64encode(png).decode("ascii")

        body = self._build_body(request, width, height, control_b64=control_b64, asset_id=asset_id)
        body_mode = str(body.get("mode", self.mode if control_b64 else "base"))
        body_steps = body.get("steps")
        body_cfg_scale = body.get("cfg_scale")
        prompt_length = len(str(body.get("prompt", "")))

        max_attempts = max(1, NVIDIA_MAX_ATTEMPTS)
        last_err = "unknown error"
        last_status = 502
        last_req_id: str | None = None
        control_image_supplied = request.control_image is not None
        gen_id = getattr(request, "generation_id", None)

        for attempt in range(1, max_attempts + 1):
            request_started_at = datetime.now(timezone.utc).isoformat()
            request_timeout_seconds = self.timeout
            t0 = time.perf_counter()
            http_status: int | None = None
            body_summary: str = ""

            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(endpoint, json=body, headers=headers)
                duration = round(time.perf_counter() - t0, 3)
                http_status = resp.status_code
                raw_text = resp.text or ""
                # Safe summary: whitespace-collapsed, base64/credentials redacted.
                body_summary = _safe_body_summary(raw_text)
                req_id = _request_id(resp.headers)
            except httpx.ConnectError as exc:
                # Connection actively refused / host unreachable (e.g. Windows
                # WinError 10061). This is NOT a timeout: nothing is listening at
                # the endpoint. Fail FAST with a clear, actionable status — a
                # refused connection will not recover within the retry window, and
                # a misleading "timeout" hides the real cause (server not running /
                # wrong NVIDIA_API_BASE). Never a fake image, never a fallback.
                duration = round(time.perf_counter() - t0, 3)
                reason = (
                    f"NVIDIA_ENDPOINT_UNREACHABLE: could not connect to {endpoint} "
                    f"({type(exc).__name__}: {str(exc)[:160]}). Nothing is listening "
                    f"there. Is the NVIDIA endpoint running and is NVIDIA_API_BASE "
                    f"('{self.base}', mode={self.deployment}) correct? For a "
                    "self-hosted NIM, start the container and confirm it listens on "
                    "that host/port; for the hosted API, set NVIDIA_API_BASE back to "
                    "https://ai.api.nvidia.com/v1/genai."
                )
                self._log_failure(
                    room_label=room_label, status=503, attempt=attempt,
                    max_attempts=max_attempts, generation_id=gen_id,
                    control_image=control_image_supplied, elapsed=duration,
                    request_id=None, error=reason,
                )
                raise AIProviderError(
                    "nvidia", reason, 503, self.model,
                    endpoint=endpoint, elapsed=duration,
                ) from exc
            except httpx.TimeoutException as exc:
                duration = round(time.perf_counter() - t0, 3)
                http_status = 504
                body_summary = f"{type(exc).__name__}: {str(exc)[:160]}"
                last_err = f"PROVIDER_TIMEOUT: NVIDIA timed out after {duration:.1f}s ({exc})"
                last_status = 504

                self._log_diagnostics(
                    room_id=room_id,
                    room_label=room_label,
                    model=self.model,
                    endpoint=endpoint,
                    prompt_length=prompt_length,
                    base_png_dimensions=base_png_dimensions,
                    base_png_byte_size=base_png_byte_size,
                    asset_upload_started=asset_upload_started,
                    asset_upload_success=asset_upload_success,
                    asset_id_present=asset_id_present,
                    request_started_at=request_started_at,
                    request_timeout_seconds=request_timeout_seconds,
                    mode=body_mode,
                    steps=body_steps,
                    width=width,
                    height=height,
                    cfg_scale=body_cfg_scale,
                    http_status=http_status,
                    body_summary=body_summary,
                    request_duration=duration,
                    retry_number=attempt,
                )

                if attempt >= max_attempts:
                    self._log_failure(
                        room_label=room_label, status=504, attempt=attempt,
                        max_attempts=max_attempts, generation_id=gen_id,
                        control_image=control_image_supplied, elapsed=duration,
                        request_id=None, error=last_err,
                    )
                    raise AIProviderError(
                        "nvidia", last_err, 504, self.model,
                        endpoint=endpoint, elapsed=duration,
                    ) from exc
                time.sleep(2.0 * (2 ** (attempt - 1)) + random.uniform(0.2, 0.8))
                continue

            self._log_diagnostics(
                room_id=room_id,
                room_label=room_label,
                model=self.model,
                endpoint=endpoint,
                prompt_length=prompt_length,
                base_png_dimensions=base_png_dimensions,
                base_png_byte_size=base_png_byte_size,
                asset_upload_started=asset_upload_started,
                asset_upload_success=asset_upload_success,
                asset_id_present=asset_id_present,
                request_started_at=request_started_at,
                request_timeout_seconds=request_timeout_seconds,
                mode=body_mode,
                steps=body_steps,
                width=width,
                height=height,
                cfg_scale=body_cfg_scale,
                http_status=http_status,
                body_summary=body_summary,
                request_duration=duration,
                retry_number=attempt,
            )

            # Every surfaced error carries actionable, key-free diagnostics:
            # status, endpoint, elapsed, and the provider's request/correlation id.
            def _err(reason: str, status: int) -> AIProviderError:
                self._log_failure(
                    room_label=room_label, status=status, attempt=attempt,
                    max_attempts=max_attempts, generation_id=gen_id,
                    control_image=control_image_supplied, elapsed=duration,
                    request_id=req_id, error=reason,
                )
                return AIProviderError(
                    "nvidia", reason, status, self.model,
                    endpoint=endpoint, elapsed=duration, request_id=req_id,
                )

            if resp.status_code in (401, 403):
                raise _err(
                    f"NVIDIA authentication failed (HTTP {resp.status_code}) — "
                    "check NVIDIA_API_KEY.",
                    resp.status_code,
                )
            if resp.status_code in (402, 429):
                if attempt < max_attempts and resp.status_code == 429:
                    delay = min(30.0, 6.0 * (2 ** (attempt - 1)) + random.uniform(0.2, 0.8))
                    logger.warning("[NVIDIA] rate-limited (429); retrying in %.1fs", delay)
                    time.sleep(delay)
                    continue
                raise _err(
                    f"NVIDIA credits/rate-limit (HTTP {resp.status_code}) — "
                    "top up credits or wait.",
                    resp.status_code,
                )
            if resp.status_code in (400, 422):
                raise _err(
                    f"NVIDIA API contract rejected the request (HTTP {resp.status_code}): "
                    f"{body_summary}. Check NVIDIA_IMAGE_MODEL='{self.model}' and whether "
                    "it supports custom image input.",
                    resp.status_code,
                )
            if resp.status_code == 404:
                raise _err(
                    "NVIDIA model/endpoint not found (HTTP 404): "
                    f"NVIDIA_IMAGE_MODEL='{self.model}'.",
                    404,
                )
            if resp.status_code == 504:
                last_err = f"PROVIDER_TIMEOUT: NVIDIA returned HTTP 504: {body_summary}"
                last_status = 504
                if attempt >= max_attempts:
                    raise _err(last_err, 504)
                time.sleep(min(3.0, 1.5 * attempt) + random.uniform(0.1, 0.4))
                continue
            if resp.status_code in _RETRYABLE:
                last_err = f"HTTP {resp.status_code}: {body_summary}"
                last_status = resp.status_code
                last_req_id = req_id
                if attempt >= max_attempts:
                    break
                time.sleep(min(3.0, 1.5 * attempt) + random.uniform(0.1, 0.4))
                continue
            if resp.status_code != 200:
                raise _err(f"NVIDIA HTTP {resp.status_code}: {body_summary}", resp.status_code)

            payload = resp.json()
            img = _extract_image(payload)
            if img is None:
                url = _image_url(payload)
                if url:
                    try:
                        with httpx.Client(timeout=self.timeout) as client:
                            dl = client.get(url)
                        if dl.status_code == 200 and dl.content and len(dl.content) >= 1000:
                            img = dl.content
                    except (httpx.TimeoutException, httpx.ConnectError) as exc:
                        raise _err(f"NVIDIA image download failed: {exc}", 502) from exc
            if img is None:
                raise _err("NVIDIA returned no image in the response", 502)
            png = _to_png(img)
            logger.info("[NVIDIA] SUCCESS — png_bytes=%d room=%s", len(png), room_label)
            return [png]

        self._log_failure(
            room_label=room_label, status=last_status, attempt=max_attempts,
            max_attempts=max_attempts, generation_id=gen_id,
            control_image=control_image_supplied, elapsed=None,
            request_id=last_req_id, error=last_err,
        )
        raise AIProviderError(
            "nvidia", f"NVIDIA generation failed: {last_err}", last_status, self.model,
            endpoint=endpoint, request_id=last_req_id,
        )
