import logging
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response

from app.core.config import MEDIA_TYPES
from app.schemas.floor_plan import (
    FloorPlanDetectionResponse,
    FloorPlanResponse,
    LayoutPayload,
)
from app.schemas.generation import GenerationRequestBody, GenerationResponse
from app.services import (
    diagnostics_service,
    generation_service,
    geometry_extraction_service,
    scene_service,
    validation_service,
)
from app.services import floor_plan_service as service
from app.services.ai import registry
from app.services.floor_plan_service import FloorPlanError

router = APIRouter(prefix="/api/floor-plans", tags=["floor-plans"])
logger = logging.getLogger("app.api.floor_plans")


@router.get("/ai-status")
def get_ai_status(provider: str | None = None) -> dict[str, Any]:
    return registry.validate_provider(provider)


@router.post("/upload", response_model=FloorPlanResponse, status_code=201)
async def upload_floor_plan(
    file: UploadFile = File(...),
    project_id: str = Form(""),
    floor_id: str = Form(""),
) -> FloorPlanResponse:
    try:
        return await service.create_floor_plan(file, project_id, floor_id)
    except FloorPlanError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("", response_model=list[FloorPlanResponse])
def list_floor_plans(
    project_id: str | None = None,
    floor_id: str | None = None,
    search: str | None = None,
) -> list[FloorPlanResponse]:
    return service.list_floor_plans(project_id, floor_id, search)


@router.get("/{file_id}", response_model=FloorPlanResponse)
def get_floor_plan(file_id: str) -> FloorPlanResponse:
    try:
        return service.get_floor_plan(file_id)
    except FloorPlanError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/{file_id}/file")
def get_floor_plan_file(file_id: str) -> FileResponse:
    try:
        path, file_type, original_filename = service.get_floor_plan_file(file_id)
    except FloorPlanError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return FileResponse(
        path,
        media_type=MEDIA_TYPES.get(file_type, "application/octet-stream"),
        filename=original_filename,
        content_disposition_type="inline",
    )


@router.get("/{file_id}/layout", response_model=LayoutPayload)
def get_layout(file_id: str) -> LayoutPayload:
    try:
        return service.get_layout(file_id)
    except FloorPlanError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.put("/{file_id}/layout", response_model=LayoutPayload)
def put_layout(file_id: str, payload: LayoutPayload) -> LayoutPayload:
    try:
        return service.save_layout(file_id, payload)
    except FloorPlanError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/{file_id}/validate")
def validate_floor_plan(file_id: str) -> dict[str, list[dict[str, Any]]]:
    try:
        canonical = service.get_canonical(file_id)
    except FloorPlanError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return {"results": validation_service.validate_canonical(canonical)}


@router.get("/{file_id}/scene")
def scene(file_id: str, version: str | None = None) -> dict[str, Any]:
    """Canonical room-scene (walls + per-room furniture) for the 3D renderer.

    By default returns the CURRENT authoritative design version's scene (with its
    ``design_version_id``) so a base-render capture binds to the live layout.

    When ``version`` (a ``design_version_id``) is supplied, the scene is built from THAT
    immutable snapshot's furniture — the exact layout the generation rendered — instead
    of the current/latest layout, so a gallery preview keeps matching its generation
    even after the plan is edited. Architectural geometry (walls/doors/windows) always
    comes from the immutable floor-plan file, so only the furniture source changes. A
    ``version`` that does not exist is a 404 — NEVER a silent fall back to the current
    scene. Reuses the existing snapshot reader; no new versioning mechanism.
    """
    try:
        if version is not None:
            canonical = service.get_version_canonical(version, file_id=file_id)
            if canonical is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"design version '{version}' not found for this floor plan",
                )
            built = scene_service.build_scene(file_id, canonical=canonical)
            built["design_version_id"] = version
            return built
        built = scene_service.build_scene(file_id)
        info = service.get_latest_version_info(file_id)
        built["design_version_id"] = info[0] if info else None
        return built
    except FloorPlanError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/{file_id}/room-eligibility")
def room_eligibility(file_id: str) -> dict[str, Any]:
    """Per-room AI-render eligibility (CONFIRMED/UNCERTAIN/EMPTY) with truthful reasons.

    Read-only: reuses the deterministic geometry gate so the UI can show, before any
    provider call, which rooms are eligible and WHY an unproven room is not — instead of
    a generic BASE_GEOMETRY_INVALID. Dynamic for any plan; no validation weakened.
    """
    try:
        return generation_service.room_eligibility(file_id)
    except FloorPlanError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/{file_id}/extraction-report")
def extraction_report(file_id: str) -> dict[str, Any]:
    """Deterministic SOURCE→CANONICAL→SCENE→VALIDATION per-room report (spec §13/§24).

    Read-only diagnostic to verify the canonical is correct BEFORE blaming the 3D
    base or the AI render: per-room furniture transforms, window wall assignment,
    duplicate/containment checks, and a CONFIRMED / UNCERTAIN / EXTRACTION_INVALID /
    WINDOW_GEOMETRY_INVALID status. No provider calls, no ML guessing, no mutation.
    """
    try:
        return diagnostics_service.build_extraction_report(file_id)
    except FloorPlanError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/{file_id}/control-image")
def control_image(file_id: str) -> Response:
    """Deterministic geometry base (walls + furniture footprints) — Phase A.

    The authoritative geometry that Phase C ControlNet will repaint without moving
    anything. Requires a vector PDF plan.
    """
    try:
        path, file_type, _ = service.get_floor_plan_file(file_id)
        canonical = service.get_canonical(file_id)
    except FloorPlanError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    if file_type != "pdf":
        raise HTTPException(status_code=422, detail="Control image requires a vector PDF plan.")
    try:
        geometry = geometry_extraction_service.extract_walls(str(path))
    except Exception as exc:  # noqa: BLE001 — surface extraction failure as 500
        raise HTTPException(status_code=500, detail=f"Geometry extraction failed: {exc}") from exc
    png = geometry_extraction_service.render_control_image(
        geometry, canonical.get("furniture", []) or []
    )
    return Response(content=png, media_type="image/png")


@router.post("/{file_id}/generate", response_model=GenerationResponse, status_code=201)
def generate(file_id: str, body: GenerationRequestBody) -> GenerationResponse:
    try:
        return generation_service.generate(
            file_id,
            body.provider,
            body.count,
            body.design_intent,
            requested_rooms=body.rooms,
            all_sections=body.all_sections,
            fresh_generation=body.fresh_generation,
            base_renders=body.base_renders,
            base_render_meta=body.base_render_meta,
        )
    except FloorPlanError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/{file_id}/generations", response_model=list[GenerationResponse])
def list_generations(file_id: str) -> list[GenerationResponse]:
    # Must NEVER 500 — a failed/partial latest generation must still list so the
    # UI can render its FAILED state (Phase 3). On an unexpected error, return an
    # empty list rather than crashing the endpoint.
    try:
        return generation_service.list_generations(file_id)
    except Exception:  # noqa: BLE001
        logger.exception("list_generations failed for %s", file_id)
        return []


@router.delete("/{file_id}")
def delete_floor_plan(file_id: str) -> dict[str, str]:
    try:
        service.delete_floor_plan(file_id)
    except FloorPlanError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return {"id": file_id, "status": "deleted"}


@router.post("/{file_id}/detect-furniture", response_model=FloorPlanDetectionResponse)
def detect_furniture(
    file_id: str,
    confidence_threshold: float = 0.20,
    apply_to_canonical: bool = False,
) -> FloorPlanDetectionResponse:
    """Detect furniture items in a floor plan using the trained YOLO model — STRICTLY
    DIAGNOSTIC.

    Returns structured detections (mm dimensions, world coords, room assignment).
    Detection NEVER becomes authoritative: the only authoritative furniture source is
    the user's manual 2D editor layout (PUT /layout). `apply_to_canonical` is kept for
    API compatibility but is inert — it never writes canonical_json, and
    `applied_to_canonical` is always false (ownership boundary, RULES 1-3).
    """
    try:
        return service.detect_furniture(
            file_id=file_id,
            confidence_threshold=confidence_threshold,
            apply_to_canonical=apply_to_canonical,
        )
    except FloorPlanError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Furniture detection failed: {exc}") from exc


@router.get("/{file_id}/debug-detection")
def debug_detection(
    file_id: str,
    confidence_threshold: float = 0.20,
) -> Response:
    """Render color-coded diagnostic expected-vs-predicted.png overlay.

    - GREEN: Correct Detection (TP)
    - RED: Missing Object (FN)
    - ORANGE: Position / Size Mismatch
    - YELLOW: Extra Object (FP)
    - PURPLE: Wrong Class
    """
    try:
        png_bytes = service.get_debug_detection_image(
            file_id=file_id,
            confidence_threshold=confidence_threshold,
        )
        return Response(content=png_bytes, media_type="image/png")
    except FloorPlanError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Debug detection rendering failed: {exc}") from exc


@router.get("/{file_id}/detection-overlay")
def detection_overlay(
    file_id: str,
    confidence_threshold: float = 0.20,
) -> Response:
    """Render detection_overlay.png with bounding boxes, labels, rotation, direction, and room/wall metrics."""
    try:
        png_bytes = service.get_detection_overlay_image(
            file_id=file_id,
            confidence_threshold=confidence_threshold,
        )
        return Response(content=png_bytes, media_type="image/png")
    except FloorPlanError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Detection overlay rendering failed: {exc}") from exc


@router.get("/{file_id}/validate-3d")
def validate_3d_projection(
    file_id: str,
    confidence_threshold: float = 0.20,
) -> dict[str, Any]:
    """Validate 3D scene placement against 2D plan via top-down orthographic projection."""
    try:
        return service.get_3d_validation_report(
            file_id=file_id,
            confidence_threshold=confidence_threshold,
        )
    except FloorPlanError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"3D validation failed: {exc}") from exc



