from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.schemas.generation import GenerationResponse
from app.services import generation_service

router = APIRouter(prefix="/api/generations", tags=["generations"])


@router.get("/{generation_id}", response_model=GenerationResponse)
def get_generation(generation_id: str) -> GenerationResponse:
    result = generation_service.get_generation(generation_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Generation not found")
    return result


@router.get("/{generation_id}/images/{index}")
def get_generation_image(generation_id: str, index: int) -> FileResponse:
    path = generation_service.image_path(generation_id, index)
    if path is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path, media_type="image/png", content_disposition_type="inline")
