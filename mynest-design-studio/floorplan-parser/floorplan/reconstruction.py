"""
3D model generation from structured floor plan data.

Converts a FloorPlan schema into a 3D mesh scene with:
- Extruded walls with proper thickness
- Door and window openings (boolean-subtracted from walls)
- Floor slabs and ceilings per room
- PBR materials for each element type
- Export to GLB/glTF (for Three.js/web) and OBJ

Uses trimesh + manifold3d for watertight boolean geometry.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
import trimesh
from shapely.geometry import LineString, Polygon
from trimesh.visual.material import PBRMaterial

from .schema import FloorPlan, Wall, Opening, OpeningType, Room
from .geometry import (
    wall_to_polygon,
    interpolate_along_centerline,
    normal_at_distance,
    compute_centerline_length,
    detect_rooms_from_walls,
)


# ── Architectural constants (meters) ──────────────────────────

WALL_HEIGHT = 2.8        # Standard residential ceiling height
FLOOR_THICKNESS = 0.12   # Floor slab thickness
CEILING_THICKNESS = 0.08 # Ceiling thickness

DOOR_HEIGHT = 2.1        # Standard door height
DOOR_DEFAULT_WIDTH = 0.9  # Standard single door width

WINDOW_SILL_HEIGHT = 0.9  # Window sill from floor
WINDOW_HEAD_HEIGHT = 2.1   # Window top from floor
WINDOW_DEFAULT_WIDTH = 1.2 # Standard window width

BOOL_MARGIN = 0.06        # Extra margin for clean boolean cuts


# ── Materials (PBR) ───────────────────────────────────────────

def _wall_material() -> PBRMaterial:
    return PBRMaterial(
        baseColorFactor=[0.92, 0.89, 0.85, 1.0],  # Warm white
        roughnessFactor=0.85,
        metallicFactor=0.0,
        name="wall",
    )


def _floor_material() -> PBRMaterial:
    return PBRMaterial(
        baseColorFactor=[0.76, 0.69, 0.57, 1.0],  # Light wood
        roughnessFactor=0.7,
        metallicFactor=0.0,
        name="floor",
    )


def _ceiling_material() -> PBRMaterial:
    return PBRMaterial(
        baseColorFactor=[0.97, 0.97, 0.97, 1.0],  # Near-white
        roughnessFactor=0.9,
        metallicFactor=0.0,
        name="ceiling",
    )


def _door_frame_material() -> PBRMaterial:
    return PBRMaterial(
        baseColorFactor=[0.55, 0.35, 0.20, 1.0],  # Dark wood
        roughnessFactor=0.6,
        metallicFactor=0.0,
        name="door_frame",
    )


def _window_frame_material() -> PBRMaterial:
    return PBRMaterial(
        baseColorFactor=[0.85, 0.85, 0.85, 1.0],  # Light grey aluminum
        roughnessFactor=0.3,
        metallicFactor=0.5,
        name="window_frame",
    )


def _glass_material() -> PBRMaterial:
    return PBRMaterial(
        baseColorFactor=[0.75, 0.85, 0.95, 0.3],  # Translucent blue
        roughnessFactor=0.1,
        metallicFactor=0.1,
        name="glass",
    )


# ── Wall mesh construction ────────────────────────────────────

def _wall_segment_to_mesh(wall: Wall, height: float = WALL_HEIGHT) -> trimesh.Trimesh:
    """Extrude a single wall's 2D polygon into a 3D wall mesh."""
    poly = wall_to_polygon(wall)
    if not poly.is_valid:
        poly = poly.buffer(0)
    mesh = trimesh.creation.extrude_polygon(poly, height=height)
    return mesh


def _make_opening_cutter(
    wall: Wall,
    opening: Opening,
    z_bottom: float,
    z_top: float,
) -> trimesh.Trimesh:
    """Create a box mesh aligned to a wall at an opening position, for boolean subtraction.
    
    The box is oriented along the wall direction, spanning the full wall thickness
    (with margin) to ensure a clean cut.
    """
    coords = wall.centerline_coords
    half_len = opening.length / 2.0
    mid_dist = opening.start + half_len
    
    # Get the center point and direction at the opening's midpoint
    center_xy = interpolate_along_centerline(coords, mid_dist)
    normal = normal_at_distance(coords, mid_dist)
    
    # Wall direction is perpendicular to normal (rotate normal 90° CW)
    wall_dir = (normal[1], -normal[0])
    angle = math.atan2(wall_dir[1], wall_dir[0])
    
    # Create rotation around Z axis
    T = trimesh.transformations.rotation_matrix(angle, [0, 0, 1])
    # Position at center of opening
    T[:3, 3] = [
        center_xy[0],
        center_xy[1],
        (z_bottom + z_top) / 2.0,
    ]
    
    cutter = trimesh.creation.box(
        extents=[
            opening.length + BOOL_MARGIN,
            wall.thickness + BOOL_MARGIN * 4,  # Extra depth for clean cut
            (z_top - z_bottom) + BOOL_MARGIN,
        ],
        transform=T,
    )
    return cutter


def _make_door_frame(
    wall: Wall,
    opening: Opening,
    height: float = DOOR_HEIGHT,
) -> trimesh.Trimesh:
    """Create a simple door frame mesh (thin border around the opening)."""
    coords = wall.centerline_coords
    mid_dist = opening.start + opening.length / 2.0
    center_xy = interpolate_along_centerline(coords, mid_dist)
    normal = normal_at_distance(coords, mid_dist)
    wall_dir = (normal[1], -normal[0])
    angle = math.atan2(wall_dir[1], wall_dir[0])
    
    frame_width = 0.05  # 5cm frame
    
    T = trimesh.transformations.rotation_matrix(angle, [0, 0, 1])
    T[:3, 3] = [center_xy[0], center_xy[1], height / 2.0]
    
    # Outer box
    outer = trimesh.creation.box(
        extents=[opening.length + frame_width * 2, wall.thickness, height],
        transform=T,
    )
    # Inner cutout
    inner = trimesh.creation.box(
        extents=[opening.length, wall.thickness + 0.02, height - frame_width],
        transform=T.copy(),
    )
    
    try:
        frame = trimesh.boolean.difference([outer, inner], engine="manifold")
        return frame
    except Exception:
        return outer  # Fallback: just the outer box


def _make_window_glass(
    wall: Wall,
    opening: Opening,
    sill_height: float = WINDOW_SILL_HEIGHT,
    head_height: float = WINDOW_HEAD_HEIGHT,
) -> trimesh.Trimesh:
    """Create a thin glass pane at a window opening."""
    coords = wall.centerline_coords
    mid_dist = opening.start + opening.length / 2.0
    center_xy = interpolate_along_centerline(coords, mid_dist)
    normal = normal_at_distance(coords, mid_dist)
    wall_dir = (normal[1], -normal[0])
    angle = math.atan2(wall_dir[1], wall_dir[0])
    
    glass_thickness = 0.01  # 1cm
    
    T = trimesh.transformations.rotation_matrix(angle, [0, 0, 1])
    T[:3, 3] = [
        center_xy[0],
        center_xy[1],
        (sill_height + head_height) / 2.0,
    ]
    
    glass = trimesh.creation.box(
        extents=[opening.length - 0.04, glass_thickness, head_height - sill_height - 0.04],
        transform=T,
    )
    return glass


# ── Floor and ceiling slabs ───────────────────────────────────

def _floor_slab(room_polygon: Polygon, thickness: float = FLOOR_THICKNESS) -> trimesh.Trimesh:
    """Create a floor slab from a room's 2D polygon."""
    if not room_polygon.is_valid:
        room_polygon = room_polygon.buffer(0)
    mesh = trimesh.creation.extrude_polygon(room_polygon, height=thickness)
    mesh.apply_translation([0, 0, -thickness])
    return mesh


def _ceiling_slab(
    room_polygon: Polygon,
    wall_height: float = WALL_HEIGHT,
    thickness: float = CEILING_THICKNESS,
) -> trimesh.Trimesh:
    """Create a ceiling slab from a room's 2D polygon."""
    if not room_polygon.is_valid:
        room_polygon = room_polygon.buffer(0)
    mesh = trimesh.creation.extrude_polygon(room_polygon, height=thickness)
    mesh.apply_translation([0, 0, wall_height])
    return mesh


# ── Main 3D generation pipeline ──────────────────────────────

def generate_3d_model(
    floorplan: FloorPlan,
    room_polygons: Optional[list[Polygon]] = None,
    wall_height: float = WALL_HEIGHT,
    include_floors: bool = True,
    include_ceilings: bool = True,
    include_door_frames: bool = True,
    include_window_glass: bool = True,
    pixels_per_meter: Optional[float] = None,
) -> trimesh.Scene:
    """Convert a FloorPlan into a 3D trimesh Scene.
    
    Args:
        floorplan: The structured floor plan data
        room_polygons: Pre-computed room polygons (from geometry engine). 
                       If None, will be detected automatically.
        wall_height: Height of walls in meters
        include_floors: Whether to generate floor slabs
        include_ceilings: Whether to generate ceiling slabs
        include_door_frames: Whether to generate door frame meshes
        include_window_glass: Whether to generate glass pane meshes
        pixels_per_meter: If set, all coordinates will be divided by this value
                         to convert from pixel space to meters
    
    Returns:
        trimesh.Scene with named geometry nodes
    """
    scene = trimesh.Scene()
    
    if not floorplan.walls:
        return scene
    
    # ── Scale from pixels to meters if needed ──
    fp = floorplan
    if pixels_per_meter and pixels_per_meter != 1.0:
        fp = _scale_floorplan(floorplan, 1.0 / pixels_per_meter)
    
    # ── Step 1: Extrude each wall independently ──
    wall_meshes = []
    for wall in fp.walls:
        try:
            mesh = _wall_segment_to_mesh(wall, height=wall_height)
            if mesh.is_volume:
                wall_meshes.append(mesh)
            else:
                # Try to repair
                trimesh.repair.fix_winding(mesh)
                trimesh.repair.fix_normals(mesh)
                mesh.fill_holes()
                wall_meshes.append(mesh)
        except Exception as e:
            print(f"Warning: could not extrude wall {wall.id}: {e}")
            continue
    
    if not wall_meshes:
        return scene
    
    # ── Step 2: Union all wall meshes ──
    try:
        if len(wall_meshes) == 1:
            walls_combined = wall_meshes[0]
        else:
            walls_combined = trimesh.boolean.union(wall_meshes, engine="manifold")
    except Exception as e:
        print(f"Warning: wall union failed ({e}), concatenating instead")
        walls_combined = trimesh.util.concatenate(wall_meshes)
    
    # ── Step 3: Cut door/window openings ──
    opening_cutters = []
    door_frames = []
    window_glasses = []
    
    for wall in fp.walls:
        for opening in wall.openings:
            if opening.type == OpeningType.DOOR:
                z_bottom = 0.0
                z_top = opening.head_height or DOOR_HEIGHT
                cutter = _make_opening_cutter(wall, opening, z_bottom, z_top)
                opening_cutters.append(cutter)
                
                if include_door_frames:
                    try:
                        frame = _make_door_frame(wall, opening, height=z_top)
                        door_frames.append(frame)
                    except Exception:
                        pass
                
            elif opening.type == OpeningType.WINDOW:
                sill = opening.sill_height or WINDOW_SILL_HEIGHT
                head = opening.head_height or WINDOW_HEAD_HEIGHT
                cutter = _make_opening_cutter(wall, opening, sill, head)
                opening_cutters.append(cutter)
                
                if include_window_glass:
                    try:
                        glass = _make_window_glass(wall, opening, sill, head)
                        window_glasses.append(glass)
                    except Exception:
                        pass
    
    # Apply boolean subtraction for openings
    if opening_cutters:
        try:
            all_cutters = trimesh.boolean.union(opening_cutters, engine="manifold")
            walls_combined = trimesh.boolean.difference(
                [walls_combined, all_cutters], engine="manifold"
            )
        except Exception as e:
            print(f"Warning: opening boolean failed ({e}), cutting individually")
            for cutter in opening_cutters:
                try:
                    walls_combined = trimesh.boolean.difference(
                        [walls_combined, cutter], engine="manifold"
                    )
                except Exception:
                    continue
    
    # Apply wall material
    walls_combined.visual = trimesh.visual.TextureVisuals(material=_wall_material())
    scene.add_geometry(walls_combined, node_name="walls", geom_name="walls")
    
    # ── Step 4: Add door frames ──
    for i, frame in enumerate(door_frames):
        frame.visual = trimesh.visual.TextureVisuals(material=_door_frame_material())
        scene.add_geometry(frame, node_name=f"door_frame_{i}", geom_name=f"door_frame_{i}")
    
    # ── Step 5: Add window glass ──
    for i, glass in enumerate(window_glasses):
        glass.visual = trimesh.visual.TextureVisuals(material=_glass_material())
        scene.add_geometry(glass, node_name=f"window_glass_{i}", geom_name=f"window_glass_{i}")
    
    # ── Step 6: Detect rooms and add floors/ceilings ──
    if room_polygons is None:
        room_polygons = detect_rooms_from_walls(fp.walls)
    else:
        # Scale room polygons if we scaled the floor plan
        if pixels_per_meter and pixels_per_meter != 1.0:
            from shapely import affinity
            scale_factor = 1.0 / pixels_per_meter
            room_polygons = [
                affinity.scale(rp, xfact=scale_factor, yfact=scale_factor, origin=(0, 0))
                for rp in room_polygons
            ]
    
    for i, rpoly in enumerate(room_polygons):
        if not rpoly.is_valid:
            rpoly = rpoly.buffer(0)
        if rpoly.area < 0.5:  # Skip tiny fragments
            continue
        
        if include_floors:
            try:
                floor = _floor_slab(rpoly)
                floor.visual = trimesh.visual.TextureVisuals(material=_floor_material())
                scene.add_geometry(floor, node_name=f"floor_{i}", geom_name=f"floor_{i}")
            except Exception as e:
                print(f"Warning: floor slab {i} failed: {e}")
        
        if include_ceilings:
            try:
                ceiling = _ceiling_slab(rpoly, wall_height=wall_height)
                ceiling.visual = trimesh.visual.TextureVisuals(material=_ceiling_material())
                scene.add_geometry(ceiling, node_name=f"ceiling_{i}", geom_name=f"ceiling_{i}")
            except Exception as e:
                print(f"Warning: ceiling slab {i} failed: {e}")
    
    return scene


def _scale_floorplan(fp: FloorPlan, scale: float) -> FloorPlan:
    """Create a scaled copy of a floor plan (all coordinates multiplied by scale)."""
    from .schema import Point2D, Wall, Opening, Room
    
    new_walls = []
    for wall in fp.walls:
        new_centerline = [
            Point2D(x=pt.x * scale, y=pt.y * scale) for pt in wall.centerline
        ]
        new_openings = [
            Opening(
                id=o.id,
                type=o.type,
                start=o.start * scale,
                length=o.length * scale,
                swing=o.swing,
                sill_height=o.sill_height,
                head_height=o.head_height,
            )
            for o in wall.openings
        ]
        new_walls.append(Wall(
            id=wall.id,
            centerline=new_centerline,
            thickness=wall.thickness * scale,
            openings=new_openings,
        ))
    
    # Don't copy rooms — they'll be recomputed from scaled walls
    return FloorPlan(
        scale=fp.scale,
        origin=Point2D(x=fp.origin.x * scale, y=fp.origin.y * scale),
        walls=new_walls,
        rooms=[],  # Will be recomputed
    )


# ── Export helpers ────────────────────────────────────────────

def export_glb(scene: trimesh.Scene, path: str) -> int:
    """Export scene to GLB (binary glTF). Returns file size in bytes."""
    glb_bytes = scene.export(file_type="glb")
    with open(path, "wb") as f:
        f.write(glb_bytes)
    return len(glb_bytes)


def export_obj(scene: trimesh.Scene, path: str) -> None:
    """Export scene to OBJ (Wavefront). Merges all geometry."""
    combined = trimesh.util.concatenate(list(scene.geometry.values()))
    combined.export(path)


def export_gltf(scene: trimesh.Scene, directory: str) -> dict:
    """Export scene to glTF (JSON + binary buffer). Returns dict of filenames."""
    import os
    os.makedirs(directory, exist_ok=True)
    gltf_dict = scene.export(file_type="gltf")
    for filename, data in gltf_dict.items():
        filepath = os.path.join(directory, filename)
        mode = "wb" if isinstance(data, bytes) else "w"
        with open(filepath, mode) as f:
            f.write(data)
    return {k: os.path.join(directory, k) for k in gltf_dict}
