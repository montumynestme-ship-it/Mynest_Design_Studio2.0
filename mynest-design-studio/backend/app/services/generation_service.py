import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image
from sqlalchemy.orm import Session

from app.db.base import session_scope
from app.db.models import AIGeneration, AIGenerationImage, DesignVersion, FloorPlan
from app.schemas.generation import GenerationImageResponse, GenerationResponse
from app.services import floor_plan_service, prompt_service
from app.services.ai import registry
from app.services.ai.base import GenerationRequest
from app.services.ai.mock_adapter import MockAdapter
from app.storage import file_storage


def _to_png(data: bytes) -> bytes:
    """Normalize provider output (flux returns JPEG) to PNG."""
    try:
        image = Image.open(BytesIO(data)).convert("RGB")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
    except Exception:  # noqa: BLE001 — fall back to raw bytes if not decodable
        return data


def _is_blank(data: bytes) -> bool:
    """True if the frame is (near) uniformly black or flat.

    NVIDIA's flux endpoint returns an all-black image when its safety filter
    blocks a prompt; such a frame must be treated as a failed render, not shown.
    """
    try:
        img = Image.open(BytesIO(data)).convert("L").resize((32, 32))
    except Exception:  # noqa: BLE001 — undecodable: let the caller keep it
        return False
    px: list[int] = list(img.getdata())
    mean = sum(px) / len(px)
    spread = max(px) - min(px)
    return bool(mean < 12 or spread < 6)  # very dark overall, or no detail at all


def _as_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return None


def _to_response(gen: AIGeneration) -> GenerationResponse:
    images = sorted(gen.images, key=lambda i: i.design_index)
    # Recompute each room's plan-space bbox from the canonical (grouping is
    # deterministic, so labels match the stored images) — no schema change needed.
    bboxes: dict[str, list[float]] = {}
    if gen.design_version is not None:
        bboxes = prompt_service.room_bboxes(gen.design_version.canonical_json or {})
    return GenerationResponse(
        id=str(gen.id),
        design_version_id=str(gen.design_version_id),
        provider=gen.provider,
        model=gen.model,
        status=gen.status,
        style=gen.style,
        created_at=gen.created_at,
        images=[
            GenerationImageResponse(
                id=str(img.id),
                url=img.image_url,
                label=img.label,
                design_index=img.design_index,
                total_designs=img.total_designs,
                bbox=bboxes.get(img.label) if img.label else None,
            )
            for img in images
        ],
    )


def _get_or_create_version(
    db: Session, fp: FloorPlan, canonical: dict[str, Any]
) -> DesignVersion:
    dv = db.query(DesignVersion).filter_by(floor_plan_id=fp.id, version_number=1).first()
    if dv is None:
        dv = DesignVersion(
            project_id=fp.project_id,
            floor_id=fp.floor_id,
            floor_plan_id=fp.id,
            version_number=1,
            canonical_json=canonical,
        )
        db.add(dv)
        db.flush()
    return dv


def _render_room(
    adapter: Any,
    provider: str,
    style: str | None,
    room: tuple[str, str, int, int],
    attempts: int = 3,
) -> tuple[str, bytes, str, str]:
    """Render one room; returns (label, png_bytes, provider_used, model).

    Retries transient provider failures (rate-limits, timeouts) with backoff before
    falling back to the demo renderer, so a single hiccup doesn't drop a real room
    to the placeholder image.
    """
    label, prompt, width, height = room
    request = GenerationRequest(prompt=prompt, style=style, count=1, width=width, height=height)
    for attempt in range(attempts):
        try:
            png = _to_png(adapter.generate(request)[0])
            if _is_blank(png):
                # Moderation-blocked/blank frame — retry with a fresh seed.
                raise ValueError("provider returned a blank/black image")
            return label, png, adapter.name, adapter.model
        except Exception:  # noqa: BLE001 — retry transient errors, then fall back below
            if attempt < attempts - 1:
                time.sleep(1.5 * (attempt + 1))
    demo = MockAdapter()
    image = demo.generate(request)[0]
    return label, _to_png(image), f"{provider} (demo fallback)", demo.model


def generate(
    file_id: str, provider: str, count: int, design_intent: dict[str, Any] | None
) -> GenerationResponse:
    # Raises FloorPlanError(404) if the plan does not exist.
    canonical = floor_plan_service.get_canonical(file_id)
    style, rooms = prompt_service.build_room_prompts(canonical, design_intent)
    rooms = rooms[:8]  # cap renders per generation

    adapter = registry.get_adapter(provider)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(lambda room: _render_room(adapter, provider, style, room), rooms)
        )

    generation_id = str(uuid.uuid4())
    total = len(results)
    for index, (_, data, _, _) in enumerate(results):
        file_storage.save_generation_image(generation_id, index, data)

    used_provider = results[0][2] if results else provider
    model = results[0][3] if results else None

    with session_scope() as db:
        fp = db.get(FloorPlan, _as_uuid(file_id))
        if fp is None:
            raise floor_plan_service.FloorPlanError(404, "Floor plan not found")
        dv = _get_or_create_version(db, fp, canonical)
        gen = AIGeneration(
            id=uuid.UUID(generation_id),
            project_id=fp.project_id,
            floor_id=fp.floor_id,
            design_version_id=dv.id,
            provider=used_provider,
            model=model,
            prompt="\n\n".join(f"[{label}]\n{prompt}" for label, prompt, _, _ in rooms),
            style=style,
            status="completed",
        )
        db.add(gen)
        for index, (label, _, _, _) in enumerate(results):
            db.add(
                AIGenerationImage(
                    generation_id=gen.id,
                    image_url=f"/api/generations/{generation_id}/images/{index}",
                    label=label,
                    design_index=index + 1,
                    total_designs=total,
                )
            )
        db.flush()
        db.refresh(gen)
        return _to_response(gen)


def list_generations(file_id: str) -> list[GenerationResponse]:
    fid = _as_uuid(file_id)
    if fid is None:
        return []
    with session_scope() as db:
        rows = (
            db.query(AIGeneration)
            .join(DesignVersion, AIGeneration.design_version_id == DesignVersion.id)
            .filter(DesignVersion.floor_plan_id == fid)
            .order_by(AIGeneration.created_at.desc())
            .all()
        )
        return [_to_response(g) for g in rows]


def get_generation(generation_id: str) -> GenerationResponse | None:
    gid = _as_uuid(generation_id)
    if gid is None:
        return None
    with session_scope() as db:
        gen = db.get(AIGeneration, gid)
        return _to_response(gen) if gen else None


def image_path(generation_id: str, index: int) -> Path | None:
    return file_storage.generation_image_path(generation_id, index)
