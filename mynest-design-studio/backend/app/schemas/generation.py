from datetime import datetime
from typing import Any

from pydantic import BaseModel


class GenerationRequestBody(BaseModel):
    provider: str = "nvidia"
    count: int = 4
    design_intent: dict[str, Any] | None = None


class GenerationImageResponse(BaseModel):
    id: str
    url: str
    label: str | None = None
    design_index: int
    total_designs: int
    # [x, y, w, h] in plan/world coordinates for this room — lets the UI crop the
    # 2D plan to the region matching this render. None if unknown.
    bbox: list[float] | None = None


class GenerationResponse(BaseModel):
    id: str
    design_version_id: str
    provider: str
    model: str | None
    status: str
    style: str | None
    created_at: datetime
    images: list[GenerationImageResponse]
