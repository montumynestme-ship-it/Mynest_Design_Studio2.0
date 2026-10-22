import logging
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import floor_plans, generations, invoices, projects
from app.core import config as ai_config
from app.db.base import init_db
from app.services.ai import fal_flux_adapter, nvidia_flux_adapter
from app.storage.file_storage import ensure_storage_ready

# Use uvicorn's own logger so the startup config line is ALWAYS visible in the
# server console (uvicorn does not attach a handler to app.* loggers by default,
# which is why an earlier version's line never appeared on restart).
logger = logging.getLogger("uvicorn.error")


def _active_ai() -> tuple[object, dict]:
    """Return (adapter_module, safe_summary) for the configured DEFAULT_AI_PROVIDER,
    so startup diagnostics and /api/ai-diagnostics describe the provider that will
    actually serve requests. Both summaries share the same keys."""
    provider = (ai_config.DEFAULT_AI_PROVIDER or "").lower()
    if provider in ("fal", "fal-flux", "fal-kontext"):
        return fal_flux_adapter, fal_flux_adapter.fal_config_summary()
    return nvidia_flux_adapter, nvidia_flux_adapter.effective_config_summary()


def _log_effective_ai_config() -> None:
    """Log the EFFECTIVE AI/NVIDIA runtime config at boot (never the API key).

    This is the ground truth for "is the running process using the current .env
    AND the current source?". If these values disagree with backend/.env, or the
    adapter module path is not this checkout, the process is STALE and must be
    restarted — the usual cause of a 500/502 that a fresh process does not
    reproduce. The API key value is never logged; only whether one is present.
    """
    adapter_mod, summary = _active_ai()
    logger.info(
        "[AI CONFIG @ startup] pid=%s python=%s adapter_module=%s "
        "provider=%s model=%s endpoint=%s mode=%s "
        "img2img_requested=%s arbitrary_image_requested=%s image_input_supported=%s "
        "conditioning_mode=%s model_capabilities=%s "
        "demo=%s deterministic_fallback=%s "
        "timeout=%.1fs max_attempts=%d room_delay=%.1fs api_key_present=%s",
        os.getpid(),
        sys.executable,
        adapter_mod.__file__,
        summary["provider"],
        summary["model"],
        summary["endpoint"],
        summary["deployment_mode"],
        summary["img2img_requested"],
        summary["arbitrary_image_requested"],
        summary["image_input_supported"],   # GENUINE capability, not the raw flag
        summary["conditioning_mode"],
        summary["model_declared_capabilities"],
        ai_config.AI_DEMO_MODE,
        ai_config.AI_ALLOW_DETERMINISTIC_FALLBACK,
        ai_config.AI_TIMEOUT_SECONDS,
        ai_config.NVIDIA_MAX_ATTEMPTS,
        ai_config.AI_ROOM_DELAY_SECONDS,
        summary["api_key_present"],
    )


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    ensure_storage_ready()
    init_db()
    _log_effective_ai_config()
    yield


app = FastAPI(title="MyNest Design Studio API", lifespan=lifespan)

# Allow the Vite dev server to call the API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health_check() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}


@app.get("/api/ai-diagnostics")
def ai_diagnostics() -> dict[str, object]:
    """Safe runtime diagnostics for confirming WHICH backend process/code is
    actually serving the browser (via the same /api proxy). Never exposes the API
    key — only whether one is configured. Hit /api/ai-diagnostics; if `pid` or
    `adapter_module` don't match your restarted process, a STALE backend is
    holding the port."""
    adapter_mod, summary = _active_ai()
    return {
        "pid": os.getpid(),
        "python": sys.executable,
        "adapter_module": adapter_mod.__file__,
        "provider": summary["provider"],
        "model": summary["model"],
        "endpoint": summary["endpoint"],                 # mode-aware (NIM -> /v1/infer)
        "deployment_mode": summary["deployment_mode"],   # "hosted" | "self_hosted_nim"
        "img2img": summary["img2img_requested"],
        "arbitrary_image": summary["arbitrary_image_requested"],
        "image_input_supported": summary["image_input_supported"],  # GENUINE capability
        "conditioning_mode": summary["conditioning_mode"],
        "model_capabilities": summary["model_declared_capabilities"],
        "demo": ai_config.AI_DEMO_MODE,
        "deterministic_fallback": ai_config.AI_ALLOW_DETERMINISTIC_FALLBACK,
        "timeout": ai_config.AI_TIMEOUT_SECONDS,
        "max_attempts": ai_config.NVIDIA_MAX_ATTEMPTS,
        "room_delay": ai_config.AI_ROOM_DELAY_SECONDS,
        "api_key_present": summary["api_key_present"],
    }


app.include_router(projects.router)
app.include_router(floor_plans.router)
app.include_router(generations.router)
app.include_router(invoices.router)
