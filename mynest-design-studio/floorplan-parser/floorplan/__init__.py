"""
floorplan — Parse floor plan images into structured wall/door/window data,
and generate 3D models from the structured representation.

Architecture:
  schema.py          — Pydantic data models (Wall, Opening, Room, FloorPlan, Corrections)
  geometry.py        — Computational geometry (wall polygons, room detection, centerline ops)
  renderer.py        — SVG + PIL rendering for visual verification and overlay
  parser.py          — VLM-based parsing with iterative correction loop
  reconstruction.py  — 3D model generation (extrude walls, cut openings, export GLB/OBJ)
"""

from .schema import (
    FloorPlan,
    Wall,
    Opening,
    OpeningType,
    DoorSwing,
    Point2D,
    Room,
    RoomLabel,
    WallFaceRef,
    WallSide,
    Correction,
    CorrectionAction,
    CorrectionResult,
)
from .geometry import (
    compute_centerline_length,
    interpolate_along_centerline,
    normal_at_distance,
    wall_to_polygon,
    wall_polygon_with_openings,
    wall_union,
    detect_rooms_from_walls,
    build_rooms,
    compute_floor_plan_geometry,
)
from .renderer import (
    render_floorplan_svg,
    render_to_image,
    overlay_on_image,
)
from .parser import (
    FloorPlanParser,
    parse_floorplan,
)
from .reconstruction import (
    generate_3d_model,
    export_glb,
    export_obj,
    export_gltf,
)

__version__ = "0.2.0"

__all__ = [
    # Schema
    "FloorPlan", "Wall", "Opening", "OpeningType", "DoorSwing",
    "Point2D", "Room", "RoomLabel", "WallFaceRef", "WallSide",
    "Correction", "CorrectionAction", "CorrectionResult",
    # Geometry
    "compute_centerline_length", "interpolate_along_centerline",
    "normal_at_distance", "wall_to_polygon", "wall_polygon_with_openings",
    "wall_union", "detect_rooms_from_walls", "build_rooms",
    "compute_floor_plan_geometry",
    # Renderer
    "render_floorplan_svg", "render_to_image", "overlay_on_image",
    # Parser
    "FloorPlanParser", "parse_floorplan",
    # 3D Reconstruction
    "generate_3d_model", "export_glb", "export_obj", "export_gltf",
]
