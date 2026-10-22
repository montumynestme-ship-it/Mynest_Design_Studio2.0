import os
from pathlib import Path

from dotenv import load_dotenv

# backend/ directory (app/core/config.py -> parents[2] == backend/).
BACKEND_DIR = Path(__file__).resolve().parents[2]

# Load backend/.env if present (never committed).
load_dotenv(BACKEND_DIR / ".env")

# PostgreSQL connection string, e.g.
#   postgresql+psycopg://USER:PASSWORD@HOST:5432/dbname
# Empty until configured — the app keeps using local JSON storage until set.
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Local file storage roots (not S3 in this phase).
STORAGE_ROOT = BACKEND_DIR / "storage"
FLOOR_PLANS_DIR = STORAGE_ROOT / "floor_plans"
GENERATIONS_DIR = STORAGE_ROOT / "generations"
RENDER_CACHE_DIR = STORAGE_ROOT / "render_cache"
DEBUG_ARTIFACTS_DIR = STORAGE_ROOT / "debug_artifacts"
ML_MODELS_DIR = STORAGE_ROOT / "models"
ML_DATASET_DIR = STORAGE_ROOT / "ml_dataset"

# ML Object Detection configuration (Phase 34 & Phase 2)
ML_ENABLED = os.getenv("ML_ENABLED", "true").lower() in ("1", "true", "yes")
ML_PROVIDER = os.getenv("ML_PROVIDER", "yolo")
ML_MODEL_PATH = os.getenv("ML_MODEL_PATH", str(ML_MODELS_DIR / "best.pt"))
ML_CONFIDENCE_THRESHOLD = float(os.getenv("ML_CONFIDENCE_THRESHOLD", "0.35"))
ML_IOU_THRESHOLD = float(os.getenv("ML_IOU_THRESHOLD", "0.50"))
ML_IMAGE_SIZE = int(os.getenv("ML_IMAGE_SIZE", "640"))
ML_MODEL_VERSION = os.getenv("ML_MODEL_VERSION", "mynest-yolo-v1")
ML_AUTO_CORRECTION = os.getenv("ML_AUTO_CORRECTION", "false").lower() in ("1", "true", "yes")

# AI provider configuration. NVIDIA-hosted Flux is text-to-image only (its hosted
# image endpoints reject an arbitrary uploaded image — example_id only). fal.ai
# FLUX.1 Kontext is a HOSTED image-EDITING provider that DOES accept an arbitrary
# input image, so it is the provider used for geometry-preserving restyle/edit.
AI_DEMO_MODE = os.getenv("AI_DEMO_MODE", "false").lower() in ("1", "true", "yes")
DEFAULT_AI_PROVIDER = os.getenv("DEFAULT_AI_PROVIDER", "nvidia")
AI_TIMEOUT_SECONDS = float(os.getenv("AI_TIMEOUT_SECONDS", "60.0"))

# ── fal.ai FLUX.1 Kontext (hosted image editing; accepts an arbitrary input image) ──
# Server-side only. Auth is `Authorization: Key <FAL_KEY>`; the key lives in
# backend/.env and is NEVER logged or returned. The input image (the deterministic
# base render) is passed as a base64 data URI in `image_url`, so NO GPU/NIM/Docker
# is needed and geometry-preserving editing works on a hosted API.
FAL_KEY = os.getenv("FAL_KEY", "")
FAL_API_BASE = os.getenv("FAL_API_BASE", "https://fal.run")
FAL_IMAGE_MODEL = os.getenv("FAL_IMAGE_MODEL", "fal-ai/flux-kontext/dev")
# fal Kontext genuinely performs image EDITING on an arbitrary uploaded image
# (unlike the hosted NVIDIA endpoints, which are example_id-only). These flags let
# diagnostics report the GENUINE capability without hardcoding it in the adapter.
FAL_IMAGE_EDIT_SUPPORTED = os.getenv("FAL_IMAGE_EDIT_SUPPORTED", "true").lower() == "true"
FAL_ARBITRARY_IMAGE_SUPPORTED = os.getenv("FAL_ARBITRARY_IMAGE_SUPPORTED", "true").lower() == "true"
# Optional img2img structure-control knobs for the edit model. UNSET by default → the
# request body is UNCHANGED (model defaults), so enabling these is an explicit, isolated
# experiment. guidance_scale tunes how strongly the edit follows the instruction; it does
# NOT provide ControlNet-style geometry lock (that needs a canny/depth model). Parsed
# leniently; an invalid value is treated as unset.
def _opt_float(name: str):
    try:
        v = os.getenv(name)
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None

def _opt_int(name: str):
    try:
        v = os.getenv(name)
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None

FAL_GUIDANCE_SCALE = _opt_float("FAL_GUIDANCE_SCALE")
FAL_NUM_INFERENCE_STEPS = _opt_int("FAL_NUM_INFERENCE_STEPS")

# ── fal.ai FLUX Control-LoRA (Canny) — REAL structural conditioning (geometry lock) ──
# This is the architectural fix for AI geometry drift. `flux-kontext/dev` is an
# instruction-EDIT model with NO structural conditioning, so it can silently move/resize
# furniture. `fal-ai/flux-control-lora-canny` is a hosted FLUX ControlNet that extracts a
# Canny edge map from a CONTROL image and LOCKS the generated image's structure to those
# edges while regenerating materials/textures/lighting from the prompt — exactly the
# geometry-preserving behaviour required. Endpoint + schema verified against the fal
# OpenAPI (fal-ai/flux-control-lora-canny): inputs prompt, control_lora_image_url,
# control_lora_strength (0-2, default 1), image_size, num_inference_steps (default 28),
# guidance_scale (default 3.5), seed, output_format. Hosted; no GPU/NIM/Docker.
# When FAL_USE_CONTROLNET is true and a control image is present, the adapter routes to
# this model instead of the edit model. One generalized path for ALL rooms (no per-room
# branching). This is an OPT-IN capability, kept available via env, but DEFAULT OFF: the
# verified/locked production model is the instruction-EDIT model `fal-ai/flux-kontext/dev`
# (image-to-image, base PNG sent as `image_url`). Set FAL_USE_CONTROLNET=true to opt into
# the Canny structure-lock path. (Restored default per the model-config regression fix.)
FAL_USE_CONTROLNET = os.getenv("FAL_USE_CONTROLNET", "false").lower() == "true"
FAL_CONTROL_MODEL = os.getenv("FAL_CONTROL_MODEL", "fal-ai/flux-control-lora-canny")
# The queue gateway (submit -> poll status -> fetch result). The ControlNet render is
# slow; the synchronous fal.run gateway holds the connection and read-times-out (and can
# re-trigger a billed generation on retry). The queue gateway returns a request_id
# immediately, so the adapter polls without a long-held connection and never double-bills.
FAL_QUEUE_BASE = os.getenv("FAL_QUEUE_BASE", "https://queue.fal.run")
# Structure-lock strength. 1.0 = follow the base render's Canny edges fully (default,
# strongest geometry preservation). Lower loosens the lock (more stylistic freedom, more
# drift). Clamped to the schema's [0, 2] in the adapter.
FAL_CONTROL_STRENGTH = _opt_float("FAL_CONTROL_STRENGTH")
# Also pass the base render as the img2img init image (`image_url`) alongside the Canny
# control. The Canny LoRA locks STRUCTURE; the init image seeds real COLORS/MATERIALS
# from the base pixels, so a high control strength can keep geometry locked while the
# surfaces render as real materials/lighting instead of flat clay — without inventing
# furniture. Both inputs are the SAME validated base render (no new geometry source).
FAL_CONTROL_USE_INIT = os.getenv("FAL_CONTROL_USE_INIT", "true").lower() == "true"

# ── NVIDIA hosted Flux image generation (NVIDIA NIM / build.nvidia.com) ──
# Server-side only. The key lives in backend/.env and is NEVER sent to the
# browser, logged, or returned in any response. Auth is `Authorization: Bearer`.
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
# NVIDIA-hosted image model. Default is the text-to-image flux.1-dev (the hosted
# API's image models are text-to-image; see NVIDIA_SUPPORTS_IMG2IMG below).
NVIDIA_IMAGE_MODEL = os.getenv("NVIDIA_IMAGE_MODEL", "black-forest-labs/flux.1-dev")
NVIDIA_API_BASE = os.getenv("NVIDIA_API_BASE", "https://ai.api.nvidia.com/v1/genai")
# Self-hosted NIM inference route. The HOSTED API is addressed as {base}/{model}
# (e.g. .../v1/genai/black-forest-labs/flux.1-dev); a SELF-HOSTED NIM instead
# exposes a fixed inference path and must NOT have the model appended. The adapter
# routes to {base}{NVIDIA_NIM_INFER_PATH} whenever NVIDIA_API_BASE is not an
# ai.api.nvidia.com host. Default "/v1/infer"; override to match your NIM's actual
# route (e.g. "/v1/images/generations" for an OpenAI-compatible NIM).
NVIDIA_NIM_INFER_PATH = os.getenv("NVIDIA_NIM_INFER_PATH", "/v1/infer")

# NVIDIA-hosted VISION LLM (OpenAI-compatible chat endpoint) used ONLY for SEMANTIC
# validation/reasoning over deterministic CV/OCR results — it never generates
# geometry and its output is schema-validated + ID-checked before use. This is a
# separate model/endpoint from the flux image adapter; no FLUX is involved. The
# vision stage is OFF by default (opt-in) so nothing calls the LLM unless enabled.
NVIDIA_VISION_ENABLED = os.getenv("NVIDIA_VISION_ENABLED", "false").lower() in (
    "1", "true", "yes",
)
NVIDIA_VISION_MODEL = os.getenv("NVIDIA_VISION_MODEL", "meta/llama-3.2-11b-vision-instruct")
NVIDIA_VISION_BASE = os.getenv("NVIDIA_VISION_BASE", "https://integrate.api.nvidia.com/v1")
# Image-to-image (geometry lock) — DEFAULT FALSE (text-to-image base mode).
#
# VERIFIED against NVIDIA's official OpenAPI contract, a live img2img probe, AND a
# passing base-mode smoke test: the HOSTED black-forest-labs/flux.1-dev endpoint
# (ai.api.nvidia.com/v1/genai/...) is TEXT-TO-IMAGE only. It accepts an `image`
# field ONLY as a predefined example (`data:image/png;example_id,{0-3}`) and
# rejects an arbitrary base64 render with HTTP 422; sending an image-conditioned
# (canny/depth/asset) payload makes NVIDIA's router hang and time out, which across
# N rooms × retries surfaces at the proxy as a bare HTTP 502 — the exact failure
# this default prevents. A clean base (text-to-image) request returns 200 in ~3s.
#
# Real image-conditioning (true geometry lock) needs a SELF-HOSTED flux.1-canny/
# depth NIM (POST /v1/infer, image=data:image/<mime>;base64,<data>). Set this true
# ONLY with NVIDIA_ARBITRARY_IMAGE_SUPPORTED=true and NVIDIA_API_BASE pointing at
# that NIM. Left FALSE, the adapter runs the working text-to-image base path and a
# failure surfaces the REAL provider error (never a fabricated/fallback image).
NVIDIA_SUPPORTS_IMG2IMG = os.getenv("NVIDIA_SUPPORTS_IMG2IMG", "false").lower() in (
    "1", "true", "yes",
)
# Which image-conditioning mode to use when NVIDIA_SUPPORTS_IMG2IMG is true:
#   canny   — ControlNet on Canny edges of the base render (locks outlines/
#             geometry hardest; best fidelity). Runs on the flux.1-dev endpoint.
#   depth   — ControlNet on a depth map (locks 3D layout; more restyle freedom).
#             Also runs on the flux.1-dev endpoint.
#   kontext — image-edit; requires NVIDIA_IMAGE_MODEL=black-forest-labs/flux.1-kontext-dev.
# Default "canny": strongest geometry lock, and works on the flux.1-dev model the
# key already has — no new model access needed.
NVIDIA_IMG2IMG_MODE = os.getenv("NVIDIA_IMG2IMG_MODE", "canny").strip().lower()

# Whether the CONFIGURED image endpoint accepts an ARBITRARY uploaded image (the
# real deterministic room PNG). VERIFIED FALSE for the hosted build.nvidia.com
# Preview API (ai.api.nvidia.com/v1/genai/black-forest-labs/flux.1-dev): its
# OpenAPI contract only accepts `image: "data:image/png;example_id,{0-3}"` — a
# predefined example set — and rejects a real base64 image with HTTP 422
# "Expected: example_id, got: base64". Arbitrary images require a SELF-HOSTED
# flux.1-dev / flux.1-canny-dev / flux.1-depth-dev NIM (from NGC), which accepts
# `image: "data:image/<mime>;base64,<data>"` at POST /v1/infer. Set this true ONLY
# when NVIDIA_API_BASE points at such a self-hosted NIM; then the adapter sends the
# base render as a real base64 image. Left FALSE (hosted), the adapter refuses the
# call with a clear NVIDIA_ARBITRARY_IMAGE_UNSUPPORTED error instead of a
# misleading 500/422.
NVIDIA_ARBITRARY_IMAGE_SUPPORTED = os.getenv(
    "NVIDIA_ARBITRARY_IMAGE_SUPPORTED", "false"
).lower() in ("1", "true", "yes")

# Seconds to wait BETWEEN sequential room generations, to stay under the
# provider's per-minute rate limit (a burst of rapid calls commonly triggers
# HTTP 429). Does not delay the first room. Set 0 to disable.
AI_ROOM_DELAY_SECONDS = float(os.getenv("AI_ROOM_DELAY_SECONDS", "4.0"))
# Max NVIDIA attempts per room (1 = no retry). Kept low so a failing multi-room
# run returns its structured error FAST — a long retry storm across N rooms
# otherwise blows past the reverse-proxy/worker timeout and surfaces as a bare
# HTTP 502 instead of the real provider error.
NVIDIA_MAX_ATTEMPTS = int(os.getenv("NVIDIA_MAX_ATTEMPTS", "2"))

# Whether an AI FAILURE may return the deterministic Three.js base render as the
# room's image. Default FALSE: a failure surfaces a real error (the base render
# must NOT masquerade as a successful AI result). Set true only for offline/demo.
AI_ALLOW_DETERMINISTIC_FALLBACK = os.getenv(
    "AI_ALLOW_DETERMINISTIC_FALLBACK", "false"
).lower() in ("1", "true", "yes")

# Experimental deterministic wall-reconstruction (app/services/wall_reconstruction.py).
# OFF by default: the algorithm is correct + scale-invariant on clean double-line
# plans (unit-tested), but on fragmented/offset real extractions it cannot close
# all rooms without fabricating walls, so it must NOT replace the honest
# furniture-bbox fallback until it passes per-plan validation. When true,
# reconstruct_rooms upgrades a room's boundary ONLY to a reconstructed polygon that
# is wall-supported AND contains that room's furniture (never fabricated, never a
# sliver); everything else keeps the existing fallback.
WALL_RECONSTRUCTION_ENABLED = os.getenv("WALL_RECONSTRUCTION_ENABLED", "false").lower() in (
    "1", "true", "yes",
)

# Upload constraints.
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB

# Allowed file extensions -> canonical file_type.
ALLOWED_EXTENSIONS: dict[str, str] = {
    ".pdf": "pdf",
    ".png": "png",
    ".jpg": "jpg",
    ".jpeg": "jpg",
    ".svg": "svg",
}

# Canonical file_type -> media type used when serving the file back.
MEDIA_TYPES: dict[str, str] = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "svg": "image/svg+xml",
}

# Incoming MIME types we accept. Generic/empty types are tolerated because
# browsers are inconsistent; the extension allow-list is the primary gate.
ALLOWED_MIME_TYPES: set[str] = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/svg+xml",
    "application/octet-stream",
    "",
}
