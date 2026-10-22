"""
Floor plan renderer — render a FloorPlan schema to SVG and/or PIL Image.

Two rendering paths:
1. SVG string output (always available, for file export / browser display)
2. PIL Image output (rasterizes via PIL ImageDraw — no system deps needed)
"""

from __future__ import annotations

import io
import math
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import Polygon, MultiPolygon

from .schema import FloorPlan, Wall, Opening, OpeningType, Room, RoomLabel
from .geometry import (
    wall_to_polygon,
    wall_polygon_with_openings,
    detect_rooms_from_walls,
    interpolate_along_centerline,
    normal_at_distance,
    compute_centerline_length,
)


# ── Color scheme ──

ROOM_COLORS: dict[RoomLabel, str] = {
    RoomLabel.BEDROOM: "#81C784",
    RoomLabel.BATHROOM: "#64B5F6",
    RoomLabel.KITCHEN: "#FFB74D",
    RoomLabel.LIVING_ROOM: "#CE93D8",
    RoomLabel.DINING_ROOM: "#F48FB1",
    RoomLabel.HALLWAY: "#E0E0E0",
    RoomLabel.CLOSET: "#BCAAA4",
    RoomLabel.LAUNDRY: "#80CBC4",
    RoomLabel.GARAGE: "#B0BEC5",
    RoomLabel.BALCONY: "#A5D6A7",
    RoomLabel.OFFICE: "#90CAF9",
    RoomLabel.STORAGE: "#D7CCC8",
    RoomLabel.ENTRANCE: "#FFF59D",
    RoomLabel.OTHER: "#CFD8DC",
    RoomLabel.UNKNOWN: "#E8EAF6",
}

WALL_COLOR = "#37474F"
WALL_STROKE = "#263238"
DOOR_COLOR = "#FF7043"
WINDOW_COLOR = "#29B6F6"
ROOM_LABEL_COLOR = "#212121"


def _hex_to_rgba(hex_color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (r, g, b, alpha)


def _shapely_poly_to_xy(poly: Polygon) -> list[tuple[float, float]]:
    return list(poly.exterior.coords)


# ──────────────────────────────────────────────
# SVG Renderer
# ──────────────────────────────────────────────

def render_floorplan_svg(
    floorplan: FloorPlan,
    width: int = 1024, height: int = 1024, padding: float = 0.5,
    show_rooms: bool = True, show_openings: bool = True, show_labels: bool = True,
    wall_opacity: float = 0.85, room_opacity: float = 0.3,
    room_polygons: Optional[list[Polygon]] = None,
) -> str:
    """Render a FloorPlan to an SVG string."""
    if not floorplan.walls:
        return f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg"></svg>'
    bbox = _compute_bbox(floorplan, padding)
    scale, tx, ty = _compute_transform(bbox, width, height)
    parts = [
        f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">',
        f'  <rect width="{width}" height="{height}" fill="white" />',
    ]
    if show_rooms:
        if room_polygons is None:
            room_polygons = detect_rooms_from_walls(floorplan.walls)
        for i, rpoly in enumerate(room_polygons):
            label = RoomLabel.UNKNOWN
            if i < len(floorplan.rooms):
                label = floorplan.rooms[i].label or RoomLabel.UNKNOWN
            color = ROOM_COLORS.get(label, ROOM_COLORS[RoomLabel.UNKNOWN])
            coords = [(tx(x), ty(y)) for x, y in rpoly.exterior.coords]
            d = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in coords) + " Z"
            parts.append(f'  <path d="{d}" fill="{color}" opacity="{room_opacity}" />')
            if show_labels:
                cx, cy = tx(rpoly.centroid.x), ty(rpoly.centroid.y)
                lt = label.value.replace("_", " ").title() if label != RoomLabel.UNKNOWN else "?"
                fs = max(10, scale * 0.25)
                parts.append(f'  <text x="{cx:.0f}" y="{cy:.0f}" text-anchor="middle" dominant-baseline="central" font-family="sans-serif" font-size="{fs:.0f}" fill="{ROOM_LABEL_COLOR}" font-weight="bold">{lt}</text>')
                parts.append(f'  <text x="{cx:.0f}" y="{cy + fs * 1.2:.0f}" text-anchor="middle" dominant-baseline="central" font-family="sans-serif" font-size="{fs * 0.7:.0f}" fill="{ROOM_LABEL_COLOR}" opacity="0.6">{rpoly.area:.1f} m\u00b2</text>')
    for wall in floorplan.walls:
        geom = wall_polygon_with_openings(wall) if (wall.openings and show_openings) else wall_to_polygon(wall)
        polys = [geom] if isinstance(geom, Polygon) else list(geom.geoms) if isinstance(geom, MultiPolygon) else []
        for poly in polys:
            coords = [(tx(x), ty(y)) for x, y in poly.exterior.coords]
            d = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in coords) + " Z"
            for interior in poly.interiors:
                hc = [(tx(x), ty(y)) for x, y in interior.coords]
                d += " M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in hc) + " Z"
            parts.append(f'  <path d="{d}" fill="{WALL_COLOR}" opacity="{wall_opacity}" stroke="{WALL_STROKE}" stroke-width="0.5" fill-rule="evenodd" />')
    if show_openings:
        for wall in floorplan.walls:
            for opening in wall.openings:
                coords = wall.centerline_coords
                half_t = wall.thickness / 2.0
                s = interpolate_along_centerline(coords, opening.start)
                e = interpolate_along_centerline(coords, opening.start + opening.length)
                n = normal_at_distance(coords, opening.start + opening.length / 2)
                color = DOOR_COLOR if opening.type == OpeningType.DOOR else WINDOW_COLOR
                sw = max(1.5, wall.thickness * scale * 0.25)
                sx, sy, ex, ey = tx(s[0]), ty(s[1]), tx(e[0]), ty(e[1])
                parts.append(f'  <line x1="{sx:.1f}" y1="{sy:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" stroke="{color}" stroke-width="{sw:.1f}" stroke-linecap="round" />')
                if opening.type == OpeningType.WINDOW:
                    off = half_t * 0.4
                    for sign in [-1, 1]:
                        parts.append(f'  <line x1="{tx(s[0]+n[0]*off*sign):.1f}" y1="{ty(s[1]+n[1]*off*sign):.1f}" x2="{tx(e[0]+n[0]*off*sign):.1f}" y2="{ty(e[1]+n[1]*off*sign):.1f}" stroke="{WINDOW_COLOR}" stroke-width="{sw*0.3:.1f}" opacity="0.7" />')
                if opening.type == OpeningType.DOOR:
                    tick = half_t * 0.8
                    for pt in [s, e]:
                        parts.append(f'  <line x1="{tx(pt[0]+n[0]*tick):.1f}" y1="{ty(pt[1]+n[1]*tick):.1f}" x2="{tx(pt[0]-n[0]*tick):.1f}" y2="{ty(pt[1]-n[1]*tick):.1f}" stroke="{color}" stroke-width="{sw*0.5:.1f}" />')
    parts.append('</svg>')
    return "\n".join(parts)


# ──────────────────────────────────────────────
# PIL Renderer
# ──────────────────────────────────────────────

def render_to_image(
    floorplan: FloorPlan,
    width: int = 1024, height: int = 1024, padding: float = 0.5,
    show_rooms: bool = True, show_openings: bool = True, show_labels: bool = True,
    wall_opacity: float = 0.85, room_opacity: float = 0.3,
    room_polygons: Optional[list[Polygon]] = None, background: str = "white",
) -> Image.Image:
    """Render floor plan to a PIL RGBA Image using ImageDraw."""
    if not floorplan.walls:
        return Image.new("RGBA", (width, height), background)
    bbox = _compute_bbox(floorplan, padding)
    scale, tx, ty = _compute_transform(bbox, width, height)
    img = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    if show_rooms:
        if room_polygons is None:
            room_polygons = detect_rooms_from_walls(floorplan.walls)
        room_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        room_draw = ImageDraw.Draw(room_layer)
        for i, rpoly in enumerate(room_polygons):
            label = RoomLabel.UNKNOWN
            if i < len(floorplan.rooms):
                label = floorplan.rooms[i].label or RoomLabel.UNKNOWN
            color = ROOM_COLORS.get(label, ROOM_COLORS[RoomLabel.UNKNOWN])
            rgba = _hex_to_rgba(color, int(255 * room_opacity))
            coords = [(tx(x), ty(y)) for x, y in rpoly.exterior.coords]
            room_draw.polygon(coords, fill=rgba)
        img = Image.alpha_composite(img, room_layer)
    wall_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    wall_draw = ImageDraw.Draw(wall_layer)
    wall_rgba = _hex_to_rgba(WALL_COLOR, int(255 * wall_opacity))
    wall_stroke_rgba = _hex_to_rgba(WALL_STROKE, int(255 * wall_opacity))
    for wall in floorplan.walls:
        geom = wall_polygon_with_openings(wall) if (wall.openings and show_openings) else wall_to_polygon(wall)
        polys = [geom] if isinstance(geom, Polygon) else list(geom.geoms) if isinstance(geom, MultiPolygon) else []
        for poly in polys:
            coords = [(tx(x), ty(y)) for x, y in poly.exterior.coords]
            wall_draw.polygon(coords, fill=wall_rgba, outline=wall_stroke_rgba)
    img = Image.alpha_composite(img, wall_layer)
    if show_openings:
        opening_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        opening_draw = ImageDraw.Draw(opening_layer)
        for wall in floorplan.walls:
            for opening in wall.openings:
                coords = wall.centerline_coords
                half_t = wall.thickness / 2.0
                s = interpolate_along_centerline(coords, opening.start)
                e = interpolate_along_centerline(coords, opening.start + opening.length)
                n = normal_at_distance(coords, opening.start + opening.length / 2)
                color = DOOR_COLOR if opening.type == OpeningType.DOOR else WINDOW_COLOR
                rgba = _hex_to_rgba(color, 230)
                lw = max(2, int(wall.thickness * scale * 0.25))
                sx, sy, ex, ey = tx(s[0]), ty(s[1]), tx(e[0]), ty(e[1])
                opening_draw.line([(sx, sy), (ex, ey)], fill=rgba, width=lw)
                if opening.type == OpeningType.WINDOW:
                    off = half_t * 0.4
                    win_rgba = _hex_to_rgba(WINDOW_COLOR, 180)
                    for sign in [-1, 1]:
                        opening_draw.line(
                            [(tx(s[0]+n[0]*off*sign), ty(s[1]+n[1]*off*sign)),
                             (tx(e[0]+n[0]*off*sign), ty(e[1]+n[1]*off*sign))],
                            fill=win_rgba, width=max(1, lw // 3))
                if opening.type == OpeningType.DOOR:
                    tick = half_t * 0.8
                    for pt in [s, e]:
                        opening_draw.line(
                            [(tx(pt[0]+n[0]*tick), ty(pt[1]+n[1]*tick)),
                             (tx(pt[0]-n[0]*tick), ty(pt[1]-n[1]*tick))],
                            fill=rgba, width=max(1, lw // 2))
        img = Image.alpha_composite(img, opening_layer)
    if show_labels:
        label_draw = ImageDraw.Draw(img)
        try:
            font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", max(10, int(scale * 0.25)))
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", max(8, int(scale * 0.18)))
            font_tiny = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", max(7, int(scale * 0.12)))
        except (OSError, IOError):
            font_large = ImageFont.load_default()
            font_small = font_large
            font_tiny = font_large
        if show_rooms and room_polygons:
            for i, rpoly in enumerate(room_polygons):
                label = RoomLabel.UNKNOWN
                if i < len(floorplan.rooms):
                    label = floorplan.rooms[i].label or RoomLabel.UNKNOWN
                lt = label.value.replace("_", " ").title() if label != RoomLabel.UNKNOWN else "?"
                cx, cy = tx(rpoly.centroid.x), ty(rpoly.centroid.y)
                label_draw.text((cx, cy), lt, fill=ROOM_LABEL_COLOR, font=font_large, anchor="mm")
                label_draw.text((cx, cy + scale * 0.35), f"{rpoly.area:.1f} m\u00b2", fill=(33, 33, 33, 150), font=font_small, anchor="mm")
        for wall in floorplan.walls:
            cl = wall.centerline_coords
            mid_d = compute_centerline_length(cl) / 2
            mid_pt = interpolate_along_centerline(cl, mid_d)
            n = normal_at_distance(cl, mid_d)
            off = wall.thickness * 0.8 + 0.15
            lx, ly = tx(mid_pt[0] + n[0] * off), ty(mid_pt[1] + n[1] * off)
            label_draw.text((lx, ly), wall.id, fill=(120, 144, 156, 180), font=font_tiny, anchor="mm")
        if show_openings:
            for wall in floorplan.walls:
                for opening in wall.openings:
                    coords = wall.centerline_coords
                    s = interpolate_along_centerline(coords, opening.start)
                    e = interpolate_along_centerline(coords, opening.start + opening.length)
                    n = normal_at_distance(coords, opening.start + opening.length / 2)
                    mx = (tx(s[0]) + tx(e[0])) / 2
                    my = (ty(s[1]) + ty(e[1])) / 2
                    off = wall.thickness * scale * 0.6
                    color = DOOR_COLOR if opening.type == OpeningType.DOOR else WINDOW_COLOR
                    label_draw.text((mx + n[0]*off, my + n[1]*off), opening.id, fill=color, font=font_tiny, anchor="mm")
    return img


def overlay_on_image(
    floorplan: FloorPlan,
    original_image: Image.Image | str,
    schema_opacity: float = 0.55,
    original_opacity: float = 0.7,
    room_polygons: Optional[list[Polygon]] = None,
    **kwargs,
) -> Image.Image:
    """Render the floor plan schema and overlay it on the original image."""
    if isinstance(original_image, str):
        original_image = Image.open(original_image)
    original_image = original_image.convert("RGBA")
    w, h = original_image.size
    rendered = render_to_image(floorplan, width=w, height=h, room_opacity=0.2, wall_opacity=0.7, room_polygons=room_polygons, **kwargs)
    r, g, b, a = rendered.split()
    a_array = np.array(a).astype(float)
    a_array = (a_array * schema_opacity).clip(0, 255).astype(np.uint8)
    rendered.putalpha(Image.fromarray(a_array))
    r_o, g_o, b_o, a_o = original_image.split()
    a_o_array = np.array(a_o).astype(float)
    a_o_array = (a_o_array * original_opacity).clip(0, 255).astype(np.uint8)
    original_dim = original_image.copy()
    original_dim.putalpha(Image.fromarray(a_o_array))
    result = Image.new("RGBA", (w, h), (255, 255, 255, 255))
    result = Image.alpha_composite(result, original_dim)
    result = Image.alpha_composite(result, rendered)
    return result


# ──────────────────────────────────────────────
# Shared helpers
# ──────────────────────────────────────────────

def _compute_bbox(floorplan: FloorPlan, padding: float) -> tuple[float, float, float, float]:
    all_coords = []
    for wall in floorplan.walls:
        poly = wall_to_polygon(wall)
        all_coords.extend(poly.exterior.coords)
    xs = [c[0] for c in all_coords]
    ys = [c[1] for c in all_coords]
    return (min(xs) - padding, min(ys) - padding, max(xs) + padding, max(ys) + padding)


def _compute_transform(bbox, width, height):
    min_x, min_y, max_x, max_y = bbox
    span_x = max_x - min_x
    span_y = max_y - min_y
    scale = min(width / span_x, height / span_y)
    used_w = span_x * scale
    used_h = span_y * scale
    offset_x = (width - used_w) / 2
    offset_y = (height - used_h) / 2
    def tx(x): return (x - min_x) * scale + offset_x
    def ty(y): return (y - min_y) * scale + offset_y
    return scale, tx, ty
