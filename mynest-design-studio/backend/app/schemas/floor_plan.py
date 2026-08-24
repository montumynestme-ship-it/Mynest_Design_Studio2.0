from datetime import datetime

from pydantic import BaseModel


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
