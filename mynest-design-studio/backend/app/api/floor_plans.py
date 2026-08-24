from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response

from app.core.config import MEDIA_TYPES
from app.schemas.floor_plan import FloorPlanResponse, LayoutPayload
from app.schemas.generation import GenerationRequestBody, GenerationResponse
from app.services import floor_plan_service as service
from app.services import (
    generation_service,
    geometry_extraction_service,
    scene_service,
    validation_service,
)
from app.services.floor_plan_service import FloorPlanError

router = APIRouter(prefix="/api/floor-plans", tags=["floor-plans"])


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
def scene(file_id: str) -> dict[str, Any]:
    """Canonical room-scene (walls + per-room furniture) for the 3D renderer."""
    try:
        return scene_service.build_scene(file_id)
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
            file_id, body.provider, body.count, body.design_intent
        )
    except FloorPlanError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/{file_id}/generations", response_model=list[GenerationResponse])
def list_generations(file_id: str) -> list[GenerationResponse]:
    return generation_service.list_generations(file_id)


@router.delete("/{file_id}")
def delete_floor_plan(file_id: str) -> dict[str, str]:
    try:
        service.delete_floor_plan(file_id)
    except FloorPlanError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return {"id": file_id, "status": "deleted"}
