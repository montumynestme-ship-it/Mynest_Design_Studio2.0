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

# AI provider keys (server-side only; never exposed to the browser).
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_IMAGE_MODEL = os.getenv("NVIDIA_IMAGE_MODEL", "black-forest-labs/flux.1-schnell")

# fal.ai — geometry-locked ControlNet img2img (Phase C). Pay-as-you-go; the
# account must have a balance or fal returns 403 "User is locked. Reason: TOP_UP".
FAL_KEY = os.getenv("FAL_KEY", "")
FAL_CONTROLNET_MODEL = os.getenv("FAL_CONTROLNET_MODEL", "fal-ai/flux-control-lora-canny")

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
