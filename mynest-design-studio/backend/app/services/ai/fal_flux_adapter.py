"""fal.ai FLUX.1 Kontext [dev] adapter — real image-to-image EDITING.

The hosted NVIDIA image endpoints are example_id-only and reject an arbitrary
uploaded render (NVIDIA_HOSTED_IMAGE_INPUT_UNSUPPORTED). fal.ai hosts FLUX.1 Kontext
as a genuine image-EDITING model that accepts an ARBITRARY input image as a base64
data URI in `image_url`, so it can restyle the deterministic base render while
preserving its geometry — hosted, no GPU/NIM/Docker required.

Contract (fal HTTP API, verified against fal docs):
  POST {FAL_API_BASE}/{FAL_IMAGE_MODEL}   e.g. https://fal.run/fal-ai/flux-kontext/dev
  Authorization: Key <FAL_KEY>
  body: {"prompt": str, "image_url": "data:image/png;base64,<...>", ...}   (edit)
        {"prompt": str, ...}                                                (text-to-image)
  200:  {"images": [{"url": str, "width": int, "height": int, "content_type": str}], ...}

The API key is server-side only and NEVER logged or returned. A failure surfaces a
real AIProviderError (never a fabricated image, never a silent fallback).
"""

import base64
import logging
import re
import time
from io import BytesIO

import httpx
from PIL import Image

from app.core.config import (
    AI_TIMEOUT_SECONDS,
    FAL_API_BASE,
    FAL_ARBITRARY_IMAGE_SUPPORTED,
    FAL_CONTROL_MODEL,
    FAL_CONTROL_STRENGTH,
    FAL_CONTROL_USE_INIT,
    FAL_GUIDANCE_SCALE,
    FAL_IMAGE_EDIT_SUPPORTED,
    FAL_IMAGE_MODEL,
    FAL_KEY,
    FAL_NUM_INFERENCE_STEPS,
    FAL_QUEUE_BASE,
    FAL_USE_CONTROLNET,
    NVIDIA_MAX_ATTEMPTS,
)
from app.services.ai.base import AIProviderAdapter, AIProviderError, GenerationRequest
# Reuse ONLY the shared image normalization. FAL has its OWN prompt builder
# (_build_fal_edit_prompt) — it must NOT use NVIDIA's _clean_prompt, whose
# NVIDIA-specific marker-stripping + length truncation discards the room identity
# and positive inventory for the FAL _EDIT_PREAMBLE + room-prompt combination.
from app.services.ai.nvidia_flux_adapter import _to_png

logger = logging.getLogger("app.services.ai.fal_flux")

# A long unbroken base64/token run (image bytes or a key) — redacted from logs.
_B64_RUN = re.compile(r"[A-Za-z0-9+/=_-]{40,}")

# Geometry-preservation preamble for the image-edit path. Leads the prompt so the
# edit restyles surfaces only and never moves/adds/removes architecture or furniture.
_EDIT_PREAMBLE = (
    "Transform this interior layout into a photorealistic premium 3D interior render. "
    "The provided image is the AUTHORITATIVE source of truth for geometry and layout; "
    "reproduce it EXACTLY and treat it as fixed. "
    "PRESERVE, without any change: the room geometry, every wall, every door, every "
    "window, the camera composition and viewpoint, and each furniture object's "
    "identity, count, position, rotation, dimensions, and room assignment. "
    "Do NOT move, resize, rotate, add, remove, duplicate, or re-arrange any wall, door, "
    "window, room, or furniture object, and do NOT invent furniture that is not already "
    "present in the image. "
    "You MAY ONLY change surface appearance: materials, textures, colors, lighting, "
    "shadows, reflections, wall/ceiling finishes, and surface realism. "
    "The final image must remain structurally and spatially identical to the input "
    "layout, with the same objects in the same places from the same camera."
)


def _safe(text: str) -> str:
    """Whitespace-collapse and redact any base64/long-token run for safe logging."""
    return _B64_RUN.sub("<redacted>", " ".join((text or "").split()))[:400]


# FAL-specific prompt scaffolding. FAL's prompt is built here (never via NVIDIA's
# _clean_prompt) so the room identity + positive inventory ALWAYS survive and lead.
_FAL_AUTHORITY = (
    "This is a photorealistic image-to-image EDIT. The provided image is the "
    "AUTHORITATIVE source of truth for the room's geometry, layout, walls, doors, "
    "windows, and furniture — reproduce it exactly and change only surface appearance."
)
_FAL_STYLE = (
    "Style: premium modern-luxury residential interior - warm 3000K concealed cove "
    "lighting, refined walnut and natural-stone finishes, boucle and linen upholstery, "
    "soft natural daylight, realistic shadows and reflections, architectural-digest "
    "photography, 8k photorealistic render."
)
_FAL_NEGATIVES = (
    "Do NOT add, remove, move, resize, rotate, duplicate, replace, or re-arrange any "
    "wall, door, window, or furniture object, and do NOT invent furniture that is not "
    "already present. Avoid fisheye, dark unlit rooms, CGI/plastic look, generic showroom."
)
# The user theme REPLACES the fixed house style when present; this is the fixed prefix of
# that styling-only block (measured so the theme can be budgeted/trimmed to fit without
# ever displacing a mandatory constraint).
_FAL_STYLE_PREFIX = (
    "STYLE (user-specified, styling only — apply to materials, colours, textures, "
    "lighting, mood and decor; it does NOT add, remove, move, resize, rotate or "
    "re-type any furniture, walls, doors or windows): "
)
# Below this many characters of surviving theme text, the styling block is dropped
# entirely rather than emit the ~180-char wrapper around a near-empty theme. Only the
# pathological case (a huge exact inventory leaving almost no budget) reaches this.
_MIN_THEME_CHARS = 16
# Extract the room label + positive inventory from the deterministic room prompt, whose
# first sentence is "...of a <room> that contains exactly: <inventory>." Deterministic,
# never hardcoded to a specific plan/room.
_ROOM_RE = re.compile(r"\bof\s+(?:a |an |the )?(.+?)\s+that\s+contains\s+exactly:", re.IGNORECASE)
_INVENTORY_RE = re.compile(r"contains\s+exactly:\s*(.+?)\.", re.IGNORECASE | re.DOTALL)
# The user-written theme (free text from the AI Render dialog) is injected by the room
# prompt builder as a single "USER THEME (styling only): …" line. Parse it so the FAL
# edit prompt carries the request's own theme instead of the fixed house style.
_THEME_RE = re.compile(r"USER THEME \(styling only\):\s*(.+?)(?:\n|$)", re.IGNORECASE)


def _parse_room_and_inventory(room_prompt: str) -> tuple[str, str]:
    """Pull (room_label, inventory) out of the room prompt. Returns ('','') if absent."""
    rp = room_prompt or ""
    room_m = _ROOM_RE.search(rp)
    inv_m = _INVENTORY_RE.search(rp)
    room = " ".join(room_m.group(1).split()).title() if room_m else ""
    inventory = " ".join(inv_m.group(1).split()) if inv_m else ""
    return room, inventory


def _parse_theme(room_prompt: str, max_len: int = 1200) -> str:
    """The user's free-text theme for THIS request, parsed from the room prompt (empty
    string when the user supplied none). Styling context only — never geometry."""
    m = _THEME_RE.search(room_prompt or "")
    return " ".join(m.group(1).split())[:max_len] if m else ""


def _collapse(text: str) -> str:
    """Single-space collapse (the per-part normalization used when joining the prompt)."""
    return " ".join((text or "").split())


def _build_fal_edit_prompt(room_prompt: str, max_len: int = 2200) -> str:
    """FAL-specific, deterministic edit prompt. Positive room identity + exact existing
    inventory lead (never relegated to negatives), followed by the geometry-preservation
    preamble, allowed visual changes, style, and the negative geometry constraints LAST.
    Does NOT use NVIDIA's _clean_prompt and NEVER drops the room identity/inventory.

    Length handling (fixes the long-theme truncation bug): the MANDATORY sections —
    authority, room, exact inventory, the geometry-preservation preamble, and the
    negative constraints — are reserved against ``max_len`` FIRST. Only the optional,
    styling-only theme/style block is then trimmed to the leftover budget, so a long
    user theme can never push ``_FAL_NEGATIVES`` (or any other mandatory section) out of
    the prompt. The negatives stay LAST (never moved before the theme) so they remain the
    final, overriding instruction and a styling theme cannot contradict them."""
    room, inventory = _parse_room_and_inventory(room_prompt)
    # MANDATORY, authoritative sections. These are never truncated; only the styling
    # block below is fitted to whatever budget remains.
    head: list[str] = [_FAL_AUTHORITY]
    if room:
        head.append(f"ROOM: {room}.")
    if inventory:
        head.append(
            f"EXACT EXISTING INVENTORY (render every one of these items and nothing "
            f"else - no extra, duplicate, missing, or invented furniture): {inventory}."
        )
    elif room_prompt:
        # Fallback: no parse match — keep the room prompt's first sentence (never the
        # 11k boilerplate, never NVIDIA truncation) so room info is not lost.
        head.append(" ".join(room_prompt.split())[:400])
    head.append(_EDIT_PREAMBLE)  # structural preservation + allowed visual changes

    # Reserve the mandatory prompt (head + negatives) FIRST. Joining inserts one space
    # between each collapsed part, so the mandatory length is computed exactly the way
    # the final join below produces it.
    mandatory_parts = [p for p in [*head, _FAL_NEGATIVES] if p]
    mandatory = " ".join(_collapse(p) for p in mandatory_parts)
    if len(mandatory) > max_len:
        # The mandatory geometry/inventory/negative constraints alone exceed the limit.
        # Fail safely (existing error contract) rather than silently drop any of them —
        # never truncate an authoritative constraint to make room.
        raise AIProviderError(
            "fal",
            f"FAL_PROMPT_TOO_LONG: mandatory geometry/inventory/negative constraints "
            f"({len(mandatory)} chars) exceed the FAL prompt limit ({max_len}); refusing "
            "to build an edit prompt that would drop an authoritative constraint.",
            422, FAL_IMAGE_MODEL,
        )

    # The styling block sits between the preamble and the negatives. Inserting it adds the
    # collapsed block plus exactly one join separator, so that is its available budget.
    style_budget = max_len - len(mandatory) - 1
    # The user's own theme REPLACES the fixed house style (never appended after it, so the
    # two can't contradict). Styling only — the preamble + negatives keep room identity,
    # exact inventory and geometry authoritative. No usable theme → fixed house style.
    theme = _parse_theme(room_prompt)
    style_block = ""
    if theme:
        avail = style_budget - len(_FAL_STYLE_PREFIX)
        if avail >= _MIN_THEME_CHARS:
            style_block = _FAL_STYLE_PREFIX + theme[:avail].rstrip()
        # else: not enough budget for a meaningful theme → drop styling, keep mandatory.
    elif len(_FAL_STYLE) <= style_budget:
        style_block = _FAL_STYLE
    # else: no theme and no room for the fixed style → mandatory-only prompt.

    parts = [*head, style_block, _FAL_NEGATIVES]
    prompt = " ".join(_collapse(p) for p in parts if p)
    # Defensive clamp — the budgeting above keeps `prompt` within `max_len` without ever
    # trimming a mandatory section, so this never fires when a style block is present; it
    # only guards against an unforeseen overrun and keeps the length contract absolute.
    if len(prompt) > max_len:
        prompt = prompt[:max_len].rstrip()
    return prompt


def run_fal_transport_diagnostic(
    tests: list[tuple[str, bytes]], attempts: int = 2,
) -> dict[str, object]:
    """Isolate provider vs transport by hitting the EXACT production fal contract
    (endpoint, model, headers, payload shape, granular timeout) with each supplied
    (label, png_bytes), `attempts` times. Returns structured, SECRET-FREE results
    (per-attempt http_status | exception_type, request_id, response_keys, elapsed_ms,
    and byte/base64 sizes) plus an evidence-based case classification. Never logs or
    returns the FAL_KEY, Authorization header, or any base64 image data."""
    import base64 as _b64
    from io import BytesIO as _BytesIO

    from PIL import Image as _Image

    endpoint = f"{(FAL_API_BASE or '').rstrip('/')}/{FAL_IMAGE_MODEL}"
    http_timeout = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)
    headers = {
        "Authorization": f"Key {FAL_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    out: list[dict[str, object]] = []
    saw_403 = saw_transport = saw_200 = False
    for label, png in tests:
        try:
            w, h = _Image.open(_BytesIO(png)).size
        except Exception:  # noqa: BLE001
            w = h = 0
        data_uri = "data:image/png;base64," + _b64.b64encode(png).decode("ascii")
        body = {"prompt": "restyle to modern contemporary, preserve geometry",
                "image_url": data_uri, "num_images": 1, "output_format": "png"}
        for attempt in range(1, attempts + 1):
            row: dict[str, object] = {
                "test": label, "attempt": attempt, "width": w, "height": h,
                "bytes": len(png), "base64_length": len(data_uri),
                "http_status": None, "exception_type": None,
                "request_id": None, "response_keys": None, "elapsed_ms": None,
            }
            t0 = time.perf_counter()
            try:
                with httpx.Client(timeout=http_timeout) as client:
                    r = client.post(endpoint, json=body, headers=headers)
                row["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
                row["http_status"] = r.status_code
                row["request_id"] = r.headers.get("x-fal-request-id") or r.headers.get("X-Fal-Request-Id")
                try:
                    j = r.json()
                    row["response_keys"] = sorted(j.keys()) if isinstance(j, dict) else None
                except Exception:  # noqa: BLE001
                    row["response_keys"] = None
                if r.status_code == 200:
                    saw_200 = True
                elif r.status_code == 403:
                    saw_403 = True
            except (httpx.RemoteProtocolError, httpx.NetworkError, httpx.TimeoutException) as exc:
                row["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
                row["exception_type"] = type(exc).__name__
                row["exception_message"] = _safe(str(exc))
                saw_transport = True
            out.append(row)
            time.sleep(0.5)
    if saw_200 and not saw_transport:
        case = "D_SUCCESS"
    elif saw_403 and not saw_transport:
        case = "A_PROVIDER_403"
    elif saw_transport and not (saw_200 or saw_403):
        case = "B_TRANSPORT_FAILURE"
    elif saw_200 and saw_transport:
        case = "C_IMAGE_SPECIFIC"
    else:
        case = "MIXED"
    return {"endpoint": endpoint, "model": FAL_IMAGE_MODEL, "attempts_each": attempts,
            "results": out, "case": case}


def fal_config_summary() -> dict[str, object]:
    """Safe diagnostics for fal (never the key). fal Kontext genuinely accepts an
    arbitrary input image and edits it, so image_input_supported/arbitrary_image are
    the GENUINE (configured) capability, not a hardcoded lie."""
    base = (FAL_API_BASE or "").rstrip("/")
    active = FAL_CONTROL_MODEL if FAL_USE_CONTROLNET else FAL_IMAGE_MODEL
    return {
        "provider": "fal",
        "model": active,
        "edit_model": FAL_IMAGE_MODEL,
        "control_model": FAL_CONTROL_MODEL,
        "endpoint": f"{base}/{active}",
        "deployment_mode": "hosted",
        "controlnet_enabled": FAL_USE_CONTROLNET,
        "img2img_requested": FAL_IMAGE_EDIT_SUPPORTED,
        "arbitrary_image_requested": FAL_ARBITRARY_IMAGE_SUPPORTED,
        "image_input_supported": bool(FAL_ARBITRARY_IMAGE_SUPPORTED and FAL_IMAGE_EDIT_SUPPORTED),
        # With ControlNet on, a supplied base render drives a Canny edge-map structure
        # lock (geometry-preserving); without it, the model instruction-edits only.
        "conditioning_mode": "canny_controlnet" if FAL_USE_CONTROLNET else "edit",
        "control_strength": (FAL_CONTROL_STRENGTH if FAL_CONTROL_STRENGTH is not None else 1.0),
        "model_declared_capabilities": (
            ["CANNY_CONTROLNET", "STRUCTURE_LOCK", "IMAGE_EDITING", "TEXT_TO_IMAGE"]
            if FAL_USE_CONTROLNET
            else ["IMAGE_EDITING", "ARBITRARY_IMAGE_INPUT", "TEXT_TO_IMAGE"]
        ),
        "api_key_present": bool(FAL_KEY),
    }


class FalFluxAdapter(AIProviderAdapter):
    name = "fal"
    model = FAL_IMAGE_MODEL
    supports_seed = True
    supports_image_reference = True
    supports_control_image = True

    def __init__(self, timeout: float = AI_TIMEOUT_SECONDS) -> None:
        self.timeout = max(timeout, 45.0)
        # Granular, BOUNDED timeouts. Image editing can run long, so the read
        # timeout is generous while connect/write stay short — a slow model is not
        # treated like a normal 10s REST call, and nothing waits forever.
        self._http_timeout = httpx.Timeout(
            connect=10.0, read=max(self.timeout, 120.0), write=30.0, pool=10.0,
        )
        self.api_key = FAL_KEY
        self.model = FAL_IMAGE_MODEL
        self.base = (FAL_API_BASE or "").rstrip("/")
        self.deployment = "hosted"
        # Genuine capability (configured), never hardcoded true.
        self.arbitrary_image_effective = bool(
            FAL_ARBITRARY_IMAGE_SUPPORTED and FAL_IMAGE_EDIT_SUPPORTED
        )

    def _endpoint(self) -> str:
        return f"{self.base}/{self.model}"

    def _control_endpoint(self) -> str:
        # Submit to the QUEUE gateway (async). The POST returns a request_id +
        # status/response URLs; _resolve_queue polls them. This avoids the sync
        # gateway's long-held connection, read-timeouts, and retry double-billing.
        return f"{(FAL_QUEUE_BASE or '').rstrip('/')}/{FAL_CONTROL_MODEL}"

    def _build_control_body(
        self, request: GenerationRequest, image_data_uri: str, width: int, height: int,
    ) -> dict:
        """Body for the fal FLUX Control-LoRA (Canny) model — REAL structural geometry
        lock. The deterministic base render is passed as `control_lora_image_url`; fal
        extracts its Canny edge map and constrains the generated image's structure to it,
        so walls/openings/furniture CANNOT drift while materials/lighting are regenerated
        from the prompt. One generalized path for every room (no per-room branches)."""
        prompt = _build_fal_edit_prompt(request.prompt)
        strength = FAL_CONTROL_STRENGTH if FAL_CONTROL_STRENGTH is not None else 1.0
        strength = max(0.0, min(2.0, float(strength)))
        body: dict[str, object] = {
            "prompt": prompt,
            "control_lora_image_url": image_data_uri,
            "control_lora_strength": strength,
            "num_images": 1,
            "output_format": "png",
            # Same validated base render as the img2img init: seeds real colors/materials
            # (so a high structure-lock does not render as flat clay) without introducing
            # any new geometry source. NOT a second/independent image.
            **({"image_url": image_data_uri} if FAL_CONTROL_USE_INIT else {}),
            # Match the output to the base render's exact pixel dimensions so the
            # deterministic furniture-box projection used by the geometry validator
            # stays valid (no rescale between base and AI output).
            "image_size": {"width": int(width), "height": int(height)},
        }
        if request.seed is not None:
            body["seed"] = request.seed
        if FAL_GUIDANCE_SCALE is not None:
            body["guidance_scale"] = FAL_GUIDANCE_SCALE
        if FAL_NUM_INFERENCE_STEPS is not None:
            body["num_inference_steps"] = FAL_NUM_INFERENCE_STEPS
        return body

    def _build_body(self, request: GenerationRequest, image_data_uri: str | None) -> dict:
        if image_data_uri is not None:
            # Image-to-image editing: FAL-specific prompt — room identity + exact
            # existing inventory lead, then geometry-preservation. NEVER NVIDIA's
            # _clean_prompt (which strips the room identity/inventory for this combo).
            prompt = _build_fal_edit_prompt(request.prompt)
            body: dict[str, object] = {"prompt": prompt, "image_url": image_data_uri}
        else:
            # Text-to-image: no source image supplied. Still FAL-specific (no NVIDIA cleaner).
            prompt = _build_fal_edit_prompt(request.prompt)
            body = {"prompt": prompt}
        body["num_images"] = 1
        body["output_format"] = "png"
        if request.seed is not None:
            body["seed"] = request.seed
        # Optional, EXPLICIT structure-control knobs (unset → model defaults, body
        # unchanged). guidance_scale tunes instruction adherence; it is NOT a ControlNet
        # geometry lock. Isolated so a single-parameter experiment is auditable.
        if FAL_GUIDANCE_SCALE is not None:
            body["guidance_scale"] = FAL_GUIDANCE_SCALE
        if FAL_NUM_INFERENCE_STEPS is not None:
            body["num_inference_steps"] = FAL_NUM_INFERENCE_STEPS
        return body

    def generate(self, request: GenerationRequest) -> list[bytes]:
        if not self.api_key:
            raise AIProviderError(
                "fal", "FAL_KEY is not configured in backend/.env", 401, self.model
            )
        room_label = getattr(request, "room_label", None) or "unknown"
        # Structural-conditioning route: when a deterministic base render is supplied and
        # FAL_USE_CONTROLNET is on, use the Canny Control-LoRA model (geometry lock)
        # instead of the instruction-edit model. This is the single generalized render
        # architecture for every room.
        use_controlnet = bool(request.control_image is not None and FAL_USE_CONTROLNET)
        endpoint = self._control_endpoint() if use_controlnet else self._endpoint()
        active_model = FAL_CONTROL_MODEL if use_controlnet else self.model

        image_data_uri: str | None = None
        ctrl_w = ctrl_h = 0
        if request.control_image is not None:
            # Genuine image-edit capability required to send an arbitrary image.
            if not self.arbitrary_image_effective:
                raise AIProviderError(
                    "fal",
                    "FAL_IMAGE_EDIT_DISABLED: a source image was supplied but fal image "
                    "editing is disabled (FAL_IMAGE_EDIT_SUPPORTED / "
                    "FAL_ARBITRARY_IMAGE_SUPPORTED). Enable them to edit the base render.",
                    422, self.model, endpoint=endpoint,
                )
            png = _to_png(request.control_image)
            image_data_uri = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
            try:
                ctrl_w, ctrl_h = Image.open(BytesIO(png)).size
            except Exception:  # noqa: BLE001
                ctrl_w = ctrl_h = 0
            # Traceable base→control evidence. _to_png RE-ENCODES, so byte identity may
            # change (never claimed); pixel identity is what holds. Record both SHAs +
            # the pixel-identity flag so the base/control relationship is auditable.
            import hashlib as _hashlib

            from io import BytesIO as _BytesIO

            from PIL import Image as _Image
            try:
                base_sha = _hashlib.sha256(request.control_image).hexdigest()
                control_sha = _hashlib.sha256(png).hexdigest()
                a = _Image.open(_BytesIO(request.control_image)).convert("RGB")
                b = _Image.open(_BytesIO(png)).convert("RGB")
                pixel_identical = (a.size == b.size and list(a.getdata()) == list(b.getdata()))
                byte_identical = (base_sha == control_sha)
                logger.info(
                    "FAL_CONTROL_IMAGE_EVIDENCE room=%s base_png_sha256=%s control_image_sha256=%s "
                    "byte_identical=%s pixel_identical=%s width=%d height=%d",
                    room_label, base_sha, control_sha, byte_identical, pixel_identical, b.size[0], b.size[1],
                )
            except Exception:  # noqa: BLE001 — evidence logging must never break generation
                pass

        if use_controlnet:
            body = self._build_control_body(request, image_data_uri, ctrl_w or 1216, ctrl_h or 832)
            conditioning_mode = "canny_controlnet"
        else:
            body = self._build_body(request, image_data_uri)
            conditioning_mode = "edit" if image_data_uri is not None else "base"
        headers = {
            "Authorization": f"Key {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            # Force a fresh, non-pooled connection per request. "Server disconnected
            # without sending a response" (RemoteProtocolError) is the classic symptom
            # of reusing a keep-alive connection the server/edge already closed; a
            # fresh client per attempt + Connection: close + HTTP/1.1 removes that race.
            "Connection": "close",
        }
        logger.info(
            "AI_RENDER_CONFIG provider=fal model=%s endpoint=%s deployment=hosted "
            "img2img_enabled=%s image_input_supported=%s control_image_present=%s "
            "conditioning_mode=%s control_strength=%s",
            active_model, endpoint, FAL_IMAGE_EDIT_SUPPORTED, self.arbitrary_image_effective,
            image_data_uri is not None, conditioning_mode,
            (FAL_CONTROL_STRENGTH if FAL_CONTROL_STRENGTH is not None else 1.0) if use_controlnet else "n/a",
        )

        # [fal REQUEST] safe diagnostic — dims / bytes / base64-length ONLY (never
        # the base64 payload, the FAL_KEY, or the Authorization header).
        req_in_w = req_in_h = 0
        req_in_bytes = len(request.control_image) if request.control_image is not None else 0
        if request.control_image is not None:
            try:
                req_in_w, req_in_h = Image.open(BytesIO(request.control_image)).size
            except Exception:  # noqa: BLE001
                pass
        logger.info(
            "[fal REQUEST] provider=fal model=%s input_width=%d input_height=%d "
            "input_bytes=%d image_base64_length=%d payload_keys=%s",
            active_model, req_in_w, req_in_h, req_in_bytes,
            len(image_data_uri) if image_data_uri else 0, sorted(body.keys()),
        )

        # fal gets at least 3 bounded attempts (spec STEP 6) so a transient transport
        # drop (RemoteProtocolError) is retried enough to reach the real provider
        # response (e.g. HTTP 403 TOP_UP) — never an infinite loop, and NVIDIA's own
        # attempt budget is untouched.
        max_attempts = max(3, NVIDIA_MAX_ATTEMPTS)
        last_err = "unknown error"
        last_status = 502
        for attempt in range(1, max_attempts + 1):
            t0 = time.perf_counter()
            try:
                with httpx.Client(timeout=self._http_timeout, http2=False) as client:
                    resp = client.post(endpoint, json=body, headers=headers)
            except httpx.ConnectError as exc:
                logger.warning(
                    "[fal TRANSPORT ERROR] exception_type=%s attempt=%d elapsed_ms=%d msg=%s",
                    type(exc).__name__, attempt, int((time.perf_counter() - t0) * 1000), str(exc)[:120],
                )
                raise AIProviderError(
                    "fal",
                    f"FAL_ENDPOINT_UNREACHABLE: could not connect to {endpoint} "
                    f"({type(exc).__name__}). Check network / FAL_API_BASE.",
                    503, self.model, endpoint=endpoint,
                ) from exc
            except httpx.TimeoutException as exc:
                logger.warning(
                    "[fal TRANSPORT ERROR] exception_type=%s attempt=%d elapsed_ms=%d msg=%s",
                    type(exc).__name__, attempt, int((time.perf_counter() - t0) * 1000), str(exc)[:120],
                )
                last_err = f"FAL_TIMEOUT: fal image generation timed out ({exc})"
                last_status = 504
                if attempt >= max_attempts:
                    raise AIProviderError(
                        "fal", last_err, 504, self.model, endpoint=endpoint,
                        elapsed=round(time.perf_counter() - t0, 3),
                    ) from exc
                time.sleep(min(3.0, 1.5 * attempt))
                continue
            except (httpx.RemoteProtocolError, httpx.NetworkError) as exc:
                # TRANSIENT transport failure — e.g. "Server disconnected without
                # sending a response" (RemoteProtocolError), a reset, or a closed
                # connection before the response. This is exactly the current error.
                # It is retried (bounded) with backoff; if it persists it surfaces as
                # a CLEAR FAL_CONNECTION_ERROR, never a generic "did not return image".
                logger.warning(
                    "[fal TRANSPORT ERROR] exception_type=%s attempt=%d elapsed_ms=%d msg=%s",
                    type(exc).__name__, attempt, int((time.perf_counter() - t0) * 1000), str(exc)[:120],
                )
                last_err = (
                    f"FAL_CONNECTION_ERROR: connection to fal dropped before a "
                    f"response ({type(exc).__name__}: {str(exc)[:160]})"
                )
                last_status = 502
                if attempt >= max_attempts:
                    raise AIProviderError(
                        "fal",
                        f"FAL_CONNECTION_ERROR: the connection to fal dropped before a "
                        f"response ({type(exc).__name__}: {str(exc)[:160]}). Transient "
                        "transport failure; if it persists, reduce request size (upload "
                        "the image instead of an inline data URI) or check the network.",
                        502, self.model, endpoint=endpoint,
                        elapsed=round(time.perf_counter() - t0, 3),
                    ) from exc
                time.sleep(min(4.0, 2.0 * attempt))
                continue

            elapsed = round(time.perf_counter() - t0, 3)
            req_id = resp.headers.get("x-fal-request-id") or resp.headers.get("X-Fal-Request-Id")
            summary = _safe(resp.text or "")
            # [fal RESPONSE] — a RECEIVED HTTP response (this is NOT a transport
            # failure; e.g. a 403 here is a provider billing/auth response, never a
            # FAL_CONNECTION_ERROR). Safe metadata only.
            try:
                _resp_keys = sorted((resp.json() or {}).keys()) if resp.status_code == 200 else None
            except Exception:  # noqa: BLE001
                _resp_keys = None
            logger.info(
                "[fal RESPONSE] attempt=%d http_status=%d request_id=%s response_keys=%s elapsed_ms=%d",
                attempt, resp.status_code, req_id, _resp_keys, int(elapsed * 1000),
            )

            if resp.status_code in (401, 403):
                raise AIProviderError(
                    "fal", f"fal authentication/authorization failed (HTTP {resp.status_code}): "
                    f"{summary}. Check FAL_KEY and that the fal account is active/funded.",
                    resp.status_code, self.model, endpoint=endpoint, elapsed=elapsed, request_id=req_id,
                )
            if resp.status_code in (402, 429):
                raise AIProviderError(
                    "fal", f"fal credits/rate-limit (HTTP {resp.status_code}): {summary}. "
                    "Top up the fal account balance or wait.",
                    resp.status_code, self.model, endpoint=endpoint, elapsed=elapsed, request_id=req_id,
                )
            if resp.status_code == 422:
                raise AIProviderError(
                    "fal", f"fal rejected the request (HTTP 422): {summary}. Check "
                    f"FAL_IMAGE_MODEL='{self.model}' and the request fields.",
                    422, self.model, endpoint=endpoint, elapsed=elapsed, request_id=req_id,
                )
            if resp.status_code != 200:
                last_err = f"fal HTTP {resp.status_code}: {summary}"
                last_status = resp.status_code
                if resp.status_code in (500, 502, 503, 504) and attempt < max_attempts:
                    time.sleep(min(3.0, 1.5 * attempt))
                    continue
                raise AIProviderError(
                    "fal", last_err, resp.status_code, self.model,
                    endpoint=endpoint, elapsed=elapsed, request_id=req_id,
                )

            try:
                payload = resp.json()
            except Exception as exc:  # noqa: BLE001
                raise AIProviderError(
                    "fal", f"fal returned non-JSON 200: {summary}", 502, self.model,
                    endpoint=endpoint, elapsed=elapsed, request_id=req_id,
                ) from exc

            # A slow model can return a QUEUE response (request_id + status/response
            # URLs) instead of the completed images — poll it to completion.
            payload = self._resolve_queue(payload, headers, endpoint, req_id)
            # fal HTTP returns images at the top level; the SDK nests under `data`.
            container = payload.get("data") if isinstance(payload.get("data"), dict) else payload
            images = (container or {}).get("images") or []
            first = images[0] if images and isinstance(images[0], dict) else {}
            url = first.get("url")
            if not url:
                keys = ",".join(sorted((payload or {}).keys()))
                raise AIProviderError(
                    "fal", f"fal returned HTTP 200 but no output image. Response keys: [{keys}]",
                    502, self.model, endpoint=endpoint, elapsed=elapsed, request_id=req_id,
                )
            raw = self._fetch_image(url, endpoint, elapsed, req_id)
            out = _to_png(raw)
            logger.info("[fal] SUCCESS png_bytes=%d room=%s elapsed=%.2fs", len(out), room_label, elapsed)
            return [out]

        raise AIProviderError(
            "fal", f"fal generation failed: {last_err}", last_status, self.model, endpoint=endpoint,
        )

    def _resolve_queue(self, payload, headers, endpoint, req_id):  # noqa: ANN001
        """If fal returned a QUEUED response (request_id + status/response URLs)
        instead of the completed images, poll the official submit->status->result
        flow with a BOUNDED timeout (never an infinite loop). Returns the completed
        result payload; a direct/nested images payload is returned unchanged."""
        if not isinstance(payload, dict):
            return payload
        has_images = bool(payload.get("images")) or (
            isinstance(payload.get("data"), dict) and payload["data"].get("images")
        )
        if has_images:
            return payload
        status_url = payload.get("status_url")
        response_url = payload.get("response_url")
        if not (status_url or response_url):
            return payload  # not a queue response — caller reports "no image"
        # The Canny ControlNet render is slow (tens of seconds to a few minutes). Poll
        # generously so a legitimately long queued job is not abandoned as a timeout
        # (the connection is NOT held open — this is cheap short-poll GETs, not a billed
        # re-submit), while still bounded so nothing waits forever.
        deadline = time.time() + max(self.timeout, 300.0)
        with httpx.Client(timeout=self._http_timeout, http2=False) as client:
            while time.time() < deadline:
                if status_url:
                    st = client.get(status_url, headers=headers)
                    if st.status_code == 200:
                        status = str((st.json() or {}).get("status", "")).upper()
                        if status in ("IN_QUEUE", "IN_PROGRESS", "PENDING"):
                            time.sleep(2.0)
                            continue
                        if status and status not in ("COMPLETED", "OK", "SUCCESS"):
                            raise AIProviderError(
                                "fal", f"fal queue status={status}", 502, self.model,
                                endpoint=endpoint, request_id=req_id,
                            )
                    else:
                        time.sleep(2.0)
                        continue
                res = client.get(response_url or status_url, headers=headers)
                if res.status_code == 200:
                    return res.json()
                if res.status_code in (202,):
                    time.sleep(2.0)
                    continue
                raise AIProviderError(
                    "fal", f"fal queue result HTTP {res.status_code}", res.status_code,
                    self.model, endpoint=endpoint, request_id=req_id,
                )
        raise AIProviderError(
            "fal", "fal image generation timed out (queue not completed)", 504,
            self.model, endpoint=endpoint, request_id=req_id,
        )

    def _fetch_image(self, url: str, endpoint: str, elapsed: float, req_id: str | None) -> bytes:
        """Return the output image bytes from an inline data URI or a hosted URL.
        Validates the payload is a real image (never saves HTML/JSON as PNG)."""
        if url.startswith("data:"):
            try:
                raw = base64.b64decode(url.split(",", 1)[1])
            except Exception as exc:  # noqa: BLE001
                raise AIProviderError(
                    "fal", "fal returned an undecodable inline image", 502, self.model,
                    endpoint=endpoint, elapsed=elapsed, request_id=req_id,
                ) from exc
        else:
            try:
                with httpx.Client(timeout=self._http_timeout, http2=False) as client:
                    dl = client.get(url)
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                raise AIProviderError(
                    "fal", f"fal image download failed: {exc}", 502, self.model,
                    endpoint=endpoint, elapsed=elapsed, request_id=req_id,
                ) from exc
            ctype = dl.headers.get("content-type", "")
            if dl.status_code != 200 or not dl.content:
                raise AIProviderError(
                    "fal", f"fal image download HTTP {dl.status_code}", 502, self.model,
                    endpoint=endpoint, elapsed=elapsed, request_id=req_id,
                )
            if not ctype.startswith("image/"):
                raise AIProviderError(
                    "fal", f"fal image URL returned non-image content-type '{ctype}' "
                    "(refusing to save HTML/JSON as an image)", 502, self.model,
                    endpoint=endpoint, elapsed=elapsed, request_id=req_id,
                )
            raw = dl.content
        # Verify the bytes are a real, openable image before accepting them.
        try:
            Image.open(BytesIO(raw)).verify()
        except Exception as exc:  # noqa: BLE001
            raise AIProviderError(
                "fal", "fal returned an invalid image payload", 502, self.model,
                endpoint=endpoint, elapsed=elapsed, request_id=req_id,
            ) from exc
        return raw
