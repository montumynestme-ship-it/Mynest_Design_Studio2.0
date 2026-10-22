"""
Floor plan schema — Pydantic models for the structured representation.

Design principles:
- Walls are first-class entities with thickness
- Openings (doors/windows) live ON walls, defined by start position + length along centerline
- Rooms are topological — defined by ordered wall-face references, not duplicate coordinates
- Curved walls are polyline-approximated centerlines (many sample points)
- Everything in meters after scale is applied
"""

from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, model_validator


class Point2D(BaseModel):
    """A 2D point in floor plan coordinates (meters from origin)."""
    x: float
    y: float

    def to_tuple(self) -> tuple[float, float]:
        return (self.x, self.y)

    @classmethod
    def from_tuple(cls, t: tuple[float, float]) -> Point2D:
        return cls(x=t[0], y=t[1])


class OpeningType(str, Enum):
    DOOR = "door"
    WINDOW = "window"


class DoorSwing(str, Enum):
    INWARD_LEFT = "inward_left"
    INWARD_RIGHT = "inward_right"
    OUTWARD_LEFT = "outward_left"
    OUTWARD_RIGHT = "outward_right"
    SLIDING = "sliding"
    DOUBLE = "double"
    UNKNOWN = "unknown"


class Opening(BaseModel):
    """A door or window on a wall, defined by position along the wall centerline."""
    id: str
    type: OpeningType
    start: float = Field(
        ...,
        description="Distance in meters along the wall centerline from the first point to the start of the opening"
    )
    length: float = Field(
        ...,
        gt=0,
        description="Length of the opening in meters along the wall centerline"
    )
    # Optional properties
    swing: Optional[DoorSwing] = None
    sill_height: Optional[float] = Field(
        None,
        description="Window sill height from floor in meters (typically 0.9-1.1m for windows, 0 for doors)"
    )
    head_height: Optional[float] = Field(
        None,
        description="Top of opening from floor in meters (typically 2.1m for doors, 2.0-2.4m for windows)"
    )


class WallSide(str, Enum):
    """Which face of a wall forms part of a room boundary.
    
    Left/right determined by walking along the centerline from first to last point:
    - LEFT = the face to your left
    - RIGHT = the face to your right
    """
    LEFT = "left"
    RIGHT = "right"


class Wall(BaseModel):
    """A wall defined by a centerline polyline + thickness.
    
    Straight walls have exactly 2 centerline points.
    Curved/angled walls have 3+ points (polyline approximation).
    The thick wall polygon is computed by buffering the centerline by thickness/2.
    """
    id: str
    centerline: list[Point2D] = Field(
        ...,
        min_length=2,
        description="Ordered points defining the wall centerline. 2 points = straight wall, 3+ = curved/angled"
    )
    thickness: float = Field(
        ...,
        gt=0,
        description="Wall thickness in meters (exterior typically 0.20-0.30, interior 0.10-0.15)"
    )
    openings: list[Opening] = Field(default_factory=list)

    @property
    def centerline_coords(self) -> list[tuple[float, float]]:
        """Centerline as list of (x, y) tuples for Shapely."""
        return [p.to_tuple() for p in self.centerline]

    @property
    def is_straight(self) -> bool:
        return len(self.centerline) == 2

    @model_validator(mode="after")
    def validate_openings_within_wall(self) -> Wall:
        """Ensure all openings fit within the wall length."""
        from .geometry import compute_centerline_length
        wall_length = compute_centerline_length(self.centerline_coords)
        for opening in self.openings:
            end = opening.start + opening.length
            if opening.start < -0.001:
                raise ValueError(
                    f"Opening {opening.id} starts before wall start "
                    f"(start={opening.start})"
                )
            if end > wall_length + 0.001:
                raise ValueError(
                    f"Opening {opening.id} extends beyond wall end "
                    f"(end={end:.3f} > wall_length={wall_length:.3f})"
                )
        return self


class WallFaceRef(BaseModel):
    """Reference to one face (side) of a wall, used to define room boundaries."""
    wall_id: str
    side: WallSide


class RoomLabel(str, Enum):
    BEDROOM = "bedroom"
    BATHROOM = "bathroom"
    KITCHEN = "kitchen"
    LIVING_ROOM = "living_room"
    DINING_ROOM = "dining_room"
    HALLWAY = "hallway"
    CLOSET = "closet"
    LAUNDRY = "laundry"
    GARAGE = "garage"
    BALCONY = "balcony"
    OFFICE = "office"
    STORAGE = "storage"
    ENTRANCE = "entrance"
    OTHER = "other"
    UNKNOWN = "unknown"


class Room(BaseModel):
    """A room defined topologically by ordered wall-face references forming a closed boundary."""
    id: str
    label: Optional[RoomLabel] = None
    boundary: list[WallFaceRef] = Field(
        ...,
        min_length=2,
        description="Ordered wall-face references forming the room boundary (must form a closed loop). "
                    "Minimum 2 walls (e.g., a curved wall + closing straight wall)."
    )
    area: Optional[float] = Field(
        None,
        description="Room area in square meters (computed from geometry)"
    )


class FloorPlan(BaseModel):
    """Complete floor plan representation."""
    scale: Optional[float] = Field(
        None,
        description="Meters per pixel/unit — used to convert from image coordinates to real-world meters. "
                    "None if coordinates are already in meters."
    )
    origin: Point2D = Field(
        default_factory=lambda: Point2D(x=0, y=0),
        description="Coordinate system origin in the source image"
    )
    walls: list[Wall] = Field(default_factory=list)
    rooms: list[Room] = Field(default_factory=list)

    def get_wall(self, wall_id: str) -> Wall | None:
        """Look up a wall by ID."""
        for w in self.walls:
            if w.id == wall_id:
                return w
        return None

    def get_room(self, room_id: str) -> Room | None:
        """Look up a room by ID."""
        for r in self.rooms:
            if r.id == room_id:
                return r
        return None

    @property
    def wall_ids(self) -> set[str]:
        return {w.id for w in self.walls}

    @model_validator(mode="after")
    def validate_room_wall_refs(self) -> FloorPlan:
        """Ensure all wall references in rooms point to existing walls."""
        wall_ids = self.wall_ids
        for room in self.rooms:
            for face_ref in room.boundary:
                if face_ref.wall_id not in wall_ids:
                    raise ValueError(
                        f"Room {room.id} references non-existent wall {face_ref.wall_id}"
                    )
        return self


class CorrectionAction(str, Enum):
    MODIFY = "modify"
    ADD = "add"
    DELETE = "delete"


class Correction(BaseModel):
    """A single field-level correction to the floor plan schema."""
    action: CorrectionAction
    target: Optional[str] = Field(
        None,
        description="Target element ID (e.g., 'w3' or 'w1.openings.d1'). Required for modify/delete."
    )
    field: Optional[str] = Field(
        None,
        description="Field to modify (e.g., 'centerline', 'thickness', 'start'). Required for modify."
    )
    value: Optional[dict | list | float | str] = Field(
        None,
        description="New value for modify, or full element spec for add."
    )
    reason: str = Field(
        ...,
        description="Human-readable explanation of why this correction is needed"
    )


class CorrectionResult(BaseModel):
    """Result of a VLM comparison between rendered overlay and original image."""
    iteration: int
    score: float = Field(
        ...,
        ge=0,
        le=1,
        description="Overall alignment confidence (0=terrible, 1=perfect)"
    )
    converged: bool = Field(
        False,
        description="Whether the schema is good enough to stop iterating"
    )
    corrections: list[Correction] = Field(default_factory=list)
