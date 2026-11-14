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
    # AIR-03 (authoritative dynamic room grouping): an OPTIONAL, user-authored
    # room-membership assignment for an open-plan item (today: a dining table that
    # the designer wants rendered as part of the Kitchen or Living Area rather than
    # as its own section). This is structured *intent* — distinct from the
    # styling-only ``room-tag`` annotation (which is stripped from grouping) and from
    # geometry-derived evidence. ``None`` = untagged (legacy designs; membership then
    # resolved/blocked by room_membership_service). Allowed values live in
    # ``room_membership_service.VALID_MEMBERSHIPS`` (KITCHEN / LIVING_AREA /
    # INDEPENDENT_DINING). Additive + nullable so it never changes a legacy item's
    # canonical fingerprint (it is dropped from serialization when None — see
    # ``floor_plan_service.save_layout``).
    room_membership: str | None = None
    # AIR-03 Step 2M.1 (explicit render inclusion): an OPTIONAL, user-authored
    # directive to INCLUDE this canonical item in a specific CONFIRMED room's
    # deterministic render even when its footprint lies OUTSIDE that room's proven
    # floor polygon (e.g. a wall-mounted kitchen counter whose alcove was not
    # reconstructed). This is RENDER INCLUSION — deliberately distinct from both the
    # canonical transform (position/size/rotation, unchanged) and the dining-only
    # ``room_membership`` disambiguation above. Value is an anchor token resolved by
    # ``room_membership_service.resolve_render_inclusions`` (today KITCHEN / LIVING_AREA)
    # to the UNIQUE CONFIRMED room carrying that anchor; anything ambiguous/absent fails
    # safe (REVIEW_REQUIRED, no move). ``None`` = no override (legacy/default). Additive +
    # nullable so it never changes a legacy item's canonical fingerprint (dropped from
    # serialization when None — see ``floor_plan_service.save_layout``). It NEVER moves,
    # resizes, rotates, re-counts, or duplicates furniture; it only changes which room's
    # render set references the (single) canonical item.
    render_room: str | None = None


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


