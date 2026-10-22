from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FloorResponse(BaseModel):
    id: str
    name: str


class ProjectResponse(BaseModel):
    id: str
    name: str
    client_name: str | None = None
    property_type: str | None = None
    floors: list[FloorResponse]


class ProjectCreate(BaseModel):
    name: str
    client_name: str | None = None
    property_type: str | None = None
    floor_count: int = 1


class LayoutItem(BaseModel):
    uid: str
    item_id: str
    cx: float
    cy: float
    w: float
    h: float
    rotation: float
    label: str | None = None


class LayoutPayload(BaseModel):
    items: list[LayoutItem] = []


class FloorPlanResponse(BaseModel):
    id: str
    original_filename: str
    filename: str
    stored_filename: str
    file_type: str
    file_size: int
    project_id: str
    floor_id: str
    project_name: str | None = None
    floor_name: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class PositionPayload(BaseModel):
    cx: float
    cy: float
    w: float
    h: float
    coordinate_frame: str = "canonical_world_px"


class NormalizedBoxPayload(BaseModel):
    cx: float
    cy: float
    w: float
    h: float


class DimensionsMmPayload(BaseModel):
    width: float
    depth: float
    detected_width_mm: float | None = None
    detected_depth_mm: float | None = None
    status: str | None = "CALIBRATED"


class FootprintPayload(BaseModel):
    width: float
    depth: float
    rotation_deg: float = 0.0


class BBoxPayload(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float


class FurnitureDetectionItem(BaseModel):
    id: str | None = None
    class_name: str = Field(..., alias="class_name")
    cls: str | None = Field(None, alias="class")
    class_id: int
    item_id: str
    confidence: float
    class_confidence: float | None = None
    position_confidence: float | None = None
    rotation_confidence: float | None = None
    size_confidence: float | None = None
    position: PositionPayload
    bbox: BBoxPayload | None = None
    footprint: FootprintPayload | None = None
    normalized: NormalizedBoxPayload
    dimensions_mm: DimensionsMmPayload
    rotation: float | None = None
    rotation_deg: float | None = None
    rotation_status: str | None = "NOT_VALIDATED"
    direction: str | None = "N"
    room_id: str | None = None
    room_assignment_method: str = "none"
    room_side: str | None = "center"
    room_side_detail: str | None = "center"
    nearest_wall_id: str | None = None
    distance_to_wall_px: float | None = None
    distance_to_wall_mm: float | None = None
    wall_orientation: str | None = None
    object_wall_angle: float | None = None
    wall_relationship: str | None = None
    relationships: list[dict[str, Any]] = []
    source_type: str = "predicted"
    validation_status: str = "PASS"
    model_version: str = "yolov8n-floorplan-v1"

    class Config:
        populate_by_name = True


class FloorPlanDetectionResponse(BaseModel):
    file_id: str
    detections: list[FurnitureDetectionItem]
    count: int
    model_version: str
    applied_to_canonical: bool = False


