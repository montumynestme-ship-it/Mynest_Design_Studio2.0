"""
Geometry engine — compute wall polygons, detect rooms, and handle centerline operations.

All operations use Shapely for robust computational geometry.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
from shapely import ops
from shapely.geometry import (
    LineString,
    MultiLineString,
    MultiPolygon,
    Point,
    Polygon,
)
from shapely.ops import polygonize, unary_union

from .schema import FloorPlan, Room, RoomLabel, Wall, WallFaceRef, WallSide, Point2D


# ──────────────────────────────────────────────
# Centerline utilities
# ──────────────────────────────────────────────

def compute_centerline_length(coords: list[tuple[float, float]]) -> float:
    """Total length of a polyline defined by coordinate pairs."""
    return LineString(coords).length


def interpolate_along_centerline(
    coords: list[tuple[float, float]],
    distance: float,
) -> tuple[float, float]:
    """Find the point at a given distance along a centerline polyline."""
    line = LineString(coords)
    pt = line.interpolate(distance)
    return (pt.x, pt.y)


def normal_at_distance(
    coords: list[tuple[float, float]],
    distance: float,
) -> tuple[float, float]:
    """Unit normal vector (pointing LEFT of travel direction) at a distance along centerline."""
    line = LineString(coords)
    eps = min(0.001, line.length * 0.001)

    d0 = max(0, distance - eps)
    d1 = min(line.length, distance + eps)
    p0 = line.interpolate(d0)
    p1 = line.interpolate(d1)

    dx = p1.x - p0.x
    dy = p1.y - p0.y
    length = math.hypot(dx, dy)
    if length < 1e-12:
        return (0.0, 1.0)

    # Left-pointing normal: rotate direction 90° CCW
    nx = -dy / length
    ny = dx / length
    return (nx, ny)


def centerline_to_linestring(wall: Wall) -> LineString:
    """Convert a Wall's centerline to a Shapely LineString."""
    return LineString(wall.centerline_coords)


# ──────────────────────────────────────────────
# Wall polygon computation
# ──────────────────────────────────────────────

def wall_to_polygon(wall: Wall) -> Polygon:
    """Compute the thick wall polygon by buffering the centerline.
    
    Uses flat end caps (cap_style=2) so wall ends are square-cut,
    enabling clean joins with adjacent walls.
    """
    line = centerline_to_linestring(wall)
    half_t = wall.thickness / 2.0
    # cap_style: 1=round, 2=flat, 3=square
    # join_style: 1=round, 2=mitre, 3=bevel
    poly = line.buffer(half_t, cap_style=2, join_style=2)
    if not poly.is_valid:
        poly = poly.buffer(0)  # fix self-intersections
    return poly


def wall_to_left_right_lines(wall: Wall) -> tuple[LineString, LineString]:
    """Compute the left and right offset lines of a wall.
    
    Left/right determined by walking along centerline from first to last point.
    Left = your left side, Right = your right side.
    
    Returns (left_line, right_line).
    """
    line = centerline_to_linestring(wall)
    half_t = wall.thickness / 2.0

    left_line = line.parallel_offset(half_t, side="left")
    right_line = line.parallel_offset(half_t, side="right")

    # Shapely's parallel_offset reverses direction for right side — fix it
    if isinstance(right_line, LineString) and len(right_line.coords) >= 2:
        # Check if right_line goes in same direction as centerline
        cl_start = np.array(line.coords[0])
        r_start = np.array(right_line.coords[0])
        r_end = np.array(right_line.coords[-1])
        if np.linalg.norm(r_end - cl_start) < np.linalg.norm(r_start - cl_start):
            right_line = LineString(list(right_line.coords)[::-1])

    return (left_line, right_line)


def wall_union(walls: list[Wall]) -> Polygon | MultiPolygon:
    """Union of all wall polygons."""
    polys = [wall_to_polygon(w) for w in walls]
    return unary_union(polys)


# ──────────────────────────────────────────────
# Opening geometry
# ──────────────────────────────────────────────

def opening_to_gap_polygon(wall: Wall, opening_idx: int) -> Polygon:
    """Compute the polygon of a door/window gap cut through a wall.
    
    The gap is a rectangle perpendicular to the wall at the opening location,
    spanning the full wall thickness.
    """
    opening = wall.openings[opening_idx]
    coords = wall.centerline_coords
    half_t = wall.thickness / 2.0

    # Get start and end points along centerline
    start_pt = interpolate_along_centerline(coords, opening.start)
    end_pt = interpolate_along_centerline(coords, opening.start + opening.length)

    # Get normals at start and end
    n_start = normal_at_distance(coords, opening.start)
    n_end = normal_at_distance(coords, opening.start + opening.length)

    # Build the gap rectangle: offset start/end points by ±half_thickness along normal
    margin = half_t * 1.1  # slight margin for clean boolean ops
    p1 = (start_pt[0] + n_start[0] * margin, start_pt[1] + n_start[1] * margin)
    p2 = (end_pt[0] + n_end[0] * margin, end_pt[1] + n_end[1] * margin)
    p3 = (end_pt[0] - n_end[0] * margin, end_pt[1] - n_end[1] * margin)
    p4 = (start_pt[0] - n_start[0] * margin, start_pt[1] - n_start[1] * margin)

    return Polygon([p1, p2, p3, p4])


def wall_polygon_with_openings(wall: Wall) -> Polygon | MultiPolygon:
    """Wall polygon with opening gaps cut out."""
    poly = wall_to_polygon(wall)
    for i in range(len(wall.openings)):
        gap = opening_to_gap_polygon(wall, i)
        poly = poly.difference(gap)
        if not poly.is_valid:
            poly = poly.buffer(0)
    return poly


# ──────────────────────────────────────────────
# Room detection
# ──────────────────────────────────────────────

def detect_rooms_from_walls(
    walls: list[Wall],
    min_area: float = 1.0,
    floor_boundary: Optional[Polygon] = None,
) -> list[Polygon]:
    """Detect rooms as enclosed regions between walls.
    
    Algorithm:
    1. Build centerline graph from all walls
    2. Use Shapely polygonize() to find all enclosed faces
    3. Filter by minimum area
    
    For thick walls, we also try the subtraction approach:
    1. Union all wall polygons
    2. Subtract from floor boundary (or convex hull)
    3. Remaining polygons = rooms
    
    Returns both approaches merged and deduplicated.
    """
    rooms: list[Polygon] = []

    # Approach 1: Centerline polygonize
    centerlines = [centerline_to_linestring(w) for w in walls]
    merged_lines = unary_union(centerlines)

    # Ensure we have a collection of lines for polygonize
    if isinstance(merged_lines, LineString):
        merged_lines = MultiLineString([merged_lines])

    centerline_rooms = list(polygonize(merged_lines))
    rooms.extend([r for r in centerline_rooms if r.area >= min_area])

    # Approach 2: Wall subtraction (handles thick walls better)
    if walls:
        all_walls = wall_union(walls)
        if floor_boundary is None:
            # Use convex hull of all wall polygons + some margin
            floor_boundary = all_walls.convex_hull.buffer(0.01)

        floor_minus_walls = floor_boundary.difference(all_walls)
        if not floor_minus_walls.is_valid:
            floor_minus_walls = floor_minus_walls.buffer(0)

        if isinstance(floor_minus_walls, MultiPolygon):
            subtraction_rooms = [
                g for g in floor_minus_walls.geoms if g.area >= min_area
            ]
        elif isinstance(floor_minus_walls, Polygon) and floor_minus_walls.area >= min_area:
            subtraction_rooms = [floor_minus_walls]
        else:
            subtraction_rooms = []

        # If centerline approach found rooms, use those (more precise topology)
        # If not, fall back to subtraction approach
        if not rooms and subtraction_rooms:
            rooms = subtraction_rooms
        elif subtraction_rooms and not rooms:
            rooms = subtraction_rooms

    return rooms


def assign_room_wall_faces(
    room_polygon: Polygon,
    walls: list[Wall],
    tolerance: float = 0.05,
) -> list[WallFaceRef]:
    """Determine which wall faces form a room's boundary.
    
    For each wall, check if the left or right offset line is adjacent to
    (within tolerance of) the room polygon boundary.
    """
    boundary_refs: list[WallFaceRef] = []
    room_boundary = room_polygon.boundary

    for wall in walls:
        left_line, right_line = wall_to_left_right_lines(wall)

        # Check if left face touches the room
        if isinstance(left_line, LineString) and left_line.length > 0:
            dist_left = left_line.distance(room_boundary)
            if dist_left < tolerance:
                boundary_refs.append(
                    WallFaceRef(wall_id=wall.id, side=WallSide.LEFT)
                )
                continue  # a wall typically only has one face per room

        # Check if right face touches the room
        if isinstance(right_line, LineString) and right_line.length > 0:
            dist_right = right_line.distance(room_boundary)
            if dist_right < tolerance:
                boundary_refs.append(
                    WallFaceRef(wall_id=wall.id, side=WallSide.RIGHT)
                )

    return boundary_refs


def build_rooms(
    walls: list[Wall],
    min_area: float = 1.0,
    floor_boundary: Optional[Polygon] = None,
) -> tuple[list[Room], list[Polygon]]:
    """Full room detection pipeline: find room polygons, assign wall faces.
    
    Returns (rooms, room_polygons) — the Room objects and their corresponding Shapely polygons.
    """
    room_polygons = detect_rooms_from_walls(
        walls, min_area=min_area, floor_boundary=floor_boundary
    )

    rooms: list[Room] = []
    for i, rpoly in enumerate(room_polygons):
        wall_faces = assign_room_wall_faces(rpoly, walls)
        room = Room(
            id=f"r{i + 1}",
            label=RoomLabel.UNKNOWN,
            boundary=wall_faces if len(wall_faces) >= 2 else wall_faces,
            area=round(rpoly.area, 2),
        )
        rooms.append(room)

    return rooms, room_polygons


# ──────────────────────────────────────────────
# Floor plan assembly
# ──────────────────────────────────────────────

def compute_floor_plan_geometry(floorplan: FloorPlan) -> dict:
    """Compute all derived geometry for a floor plan.
    
    Returns dict with:
    - wall_polygons: {wall_id: Polygon}
    - wall_polygons_with_openings: {wall_id: Polygon|MultiPolygon}
    - room_polygons: [Polygon]
    - wall_union: Polygon|MultiPolygon
    """
    wall_polys = {}
    wall_polys_openings = {}

    for wall in floorplan.walls:
        wall_polys[wall.id] = wall_to_polygon(wall)
        if wall.openings:
            wall_polys_openings[wall.id] = wall_polygon_with_openings(wall)
        else:
            wall_polys_openings[wall.id] = wall_polys[wall.id]

    all_walls = unary_union(list(wall_polys.values())) if wall_polys else Polygon()

    room_polygons = detect_rooms_from_walls(floorplan.walls)

    return {
        "wall_polygons": wall_polys,
        "wall_polygons_with_openings": wall_polys_openings,
        "room_polygons": room_polygons,
        "wall_union": all_walls,
    }
