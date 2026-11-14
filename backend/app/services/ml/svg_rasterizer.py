"""SVG Rasterizer for Furniture Library shapes.

Parses and rasterizes the 14 canonical furniture SVGs from frontend/public/furniture
directly into PIL RGBA images at exact pixel dimensions. Provides fallback procedural
architectural rendering to guarantee zero external C-dependency requirements.
"""

import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from app.core.config import BACKEND_DIR
from app.data.classes import CLASS_BY_ITEM_ID, MLClassInfo

# Path to frontend furniture SVG assets
SVG_DIR = BACKEND_DIR.parent / "frontend" / "public" / "furniture"

# In-memory raster cache: (item_id, target_w, target_h) -> PIL Image (RGBA)
_RASTER_CACHE: dict[tuple[str, int, int], Image.Image] = {}


def _parse_color(val: str | None, default: str = "#000000") -> str | tuple[int, int, int, int] | None:
    if not val or val == "none":
        return None
    val = val.strip()
    if val.startswith("#"):
        if len(val) == 4:  # #abc -> #aabbcc
            val = "#" + "".join(c * 2 for c in val[1:])
        try:
            r = int(val[1:3], 16)
            g = int(val[3:5], 16)
            b = int(val[5:7], 16)
            return (r, g, b, 255)
        except ValueError:
            return default
    return val


def _parse_path_d(d_str: str) -> list[tuple[str, list[float]]]:
    """Tokenize SVG path d string into commands and coordinates."""
    tokens = re.findall(r"([MmLlHhVvQqCcZz]|[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?)", d_str)
    commands: list[tuple[str, list[float]]] = []
    current_cmd = ""
    current_coords: list[float] = []

    for t in tokens:
        if t.isalpha():
            if current_cmd:
                commands.append((current_cmd, current_coords))
            current_cmd = t
            current_coords = []
        else:
            current_coords.append(float(t))

    if current_cmd:
        commands.append((current_cmd, current_coords))
    return commands


def render_svg_to_image(svg_path: Path, target_w: int, target_h: int) -> Image.Image:
    """Rasterize an SVG file containing rect, circle, line, path into RGBA PIL Image."""
    target_w = max(4, int(target_w))
    target_h = max(4, int(target_h))
    img = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    try:
        tree = ET.parse(svg_path)
        root = tree.getroot()

        # Determine viewBox or width/height
        view_box = root.attrib.get("viewBox")
        if view_box:
            vb_parts = [float(x) for x in view_box.replace(",", " ").split()]
            _, _, src_w, src_h = vb_parts
        else:
            src_w = float(root.attrib.get("width", 100))
            src_h = float(root.attrib.get("height", 100))

        sx = target_w / max(src_w, 1.0)
        sy = target_h / max(src_h, 1.0)

        # Iterate elements
        for elem in root.iter():
            tag = elem.tag.split("}")[-1].lower()

            fill_val = _parse_color(elem.attrib.get("fill"))
            stroke_val = _parse_color(elem.attrib.get("stroke"))
            sw = float(elem.attrib.get("stroke-width", 2.0)) * (sx + sy) / 2.0
            stroke_w = max(1, int(round(sw))) if stroke_val else 0

            if tag == "rect":
                rx = float(elem.attrib.get("x", 0)) * sx
                ry = float(elem.attrib.get("y", 0)) * sy
                rw = float(elem.attrib.get("width", 0)) * sx
                rh = float(elem.attrib.get("height", 0)) * sy
                crx = float(elem.attrib.get("rx", 0)) * sx

                box = [rx, ry, rx + rw, ry + rh]
                if crx > 0:
                    draw.rounded_rectangle(box, radius=int(crx), fill=fill_val, outline=stroke_val, width=stroke_w)
                else:
                    draw.rectangle(box, fill=fill_val, outline=stroke_val, width=stroke_w)

            elif tag == "circle":
                cx = float(elem.attrib.get("cx", 0)) * sx
                cy = float(elem.attrib.get("cy", 0)) * sy
                r = float(elem.attrib.get("r", 0)) * (sx + sy) / 2.0
                draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill_val, outline=stroke_val, width=stroke_w)

            elif tag == "line":
                x1 = float(elem.attrib.get("x1", 0)) * sx
                y1 = float(elem.attrib.get("y1", 0)) * sy
                x2 = float(elem.attrib.get("x2", 0)) * sx
                y2 = float(elem.attrib.get("y2", 0)) * sy
                if stroke_val:
                    draw.line([(x1, y1), (x2, y2)], fill=stroke_val, width=stroke_w)

            elif tag == "path":
                d_str = elem.attrib.get("d", "")
                commands = _parse_path_d(d_str)
                pts: list[tuple[float, float]] = []
                cur_x, cur_y = 0.0, 0.0

                for cmd, coords in commands:
                    if cmd in ("M", "m"):
                        if coords:
                            cur_x = coords[0] * sx if cmd == "M" else cur_x + coords[0] * sx
                            cur_y = coords[1] * sy if cmd == "M" else cur_y + coords[1] * sy
                            pts.append((cur_x, cur_y))
                    elif cmd in ("L", "l"):
                        if coords:
                            cur_x = coords[0] * sx if cmd == "L" else cur_x + coords[0] * sx
                            cur_y = coords[1] * sy if cmd == "L" else cur_y + coords[1] * sy
                            pts.append((cur_x, cur_y))
                    elif cmd in ("H", "h"):
                        if coords:
                            cur_x = coords[0] * sx if cmd == "H" else cur_x + coords[0] * sx
                            pts.append((cur_x, cur_y))
                    elif cmd in ("V", "v"):
                        if coords:
                            cur_y = coords[0] * sy if cmd == "V" else cur_y + coords[0] * sy
                            pts.append((cur_x, cur_y))
                    elif cmd in ("Q", "q"):
                        # Quadratic bezier: approximate with control and end point
                        if len(coords) >= 4:
                            ex = coords[2] * sx if cmd == "Q" else cur_x + coords[2] * sx
                            ey = coords[3] * sy if cmd == "Q" else cur_y + coords[3] * sy
                            pts.append((ex, ey))
                            cur_x, cur_y = ex, ey

                if len(pts) >= 2 and stroke_val:
                    draw.line(pts, fill=stroke_val, width=stroke_w)

    except Exception:
        # If any SVG parsing fails, render a clean architectural plan symbol
        draw.rectangle([2, 2, target_w - 3, target_h - 3], fill=(245, 240, 230, 255), outline=(110, 75, 45, 255), width=2)

    return img


def render_procedural_furniture(info: MLClassInfo, target_w: int, target_h: int) -> Image.Image:
    """Procedural fallback renderer for architectural floor-plan symbols."""
    target_w = max(4, int(target_w))
    target_h = max(4, int(target_h))
    img = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    r, g, b = info.color_rgb
    fill_col = (r, g, b, 220)
    stroke_col = (max(0, r - 50), max(0, g - 50), max(0, b - 50), 255)

    kind = info.kind
    if kind == "bed":
        # Mattress + 2 pillows + fold
        draw.rounded_rectangle([2, 2, target_w - 3, target_h - 3], radius=4, fill=(251, 247, 241, 255), outline=stroke_col, width=3)
        pw = max(4, int(target_w * 0.36))
        ph = max(4, int(target_h * 0.20))
        draw.rectangle([int(target_w * 0.1), int(target_h * 0.08), int(target_w * 0.1) + pw, int(target_h * 0.08) + ph], fill=(235, 220, 200, 255), outline=stroke_col, width=1)
        draw.rectangle([int(target_w * 0.54), int(target_h * 0.08), int(target_w * 0.54) + pw, int(target_h * 0.08) + ph], fill=(235, 220, 200, 255), outline=stroke_col, width=1)
        draw.line([(2, int(target_h * 0.4)), (target_w - 3, int(target_h * 0.4))], fill=stroke_col, width=2)
    elif kind == "sofa":
        # Back cushion + armrests + seating cushion
        draw.rounded_rectangle([2, 2, target_w - 3, target_h - 3], radius=6, fill=(240, 235, 225, 255), outline=stroke_col, width=3)
        draw.rectangle([2, 2, target_w - 3, int(target_h * 0.35)], fill=(225, 215, 200, 255), outline=stroke_col, width=2)
    elif kind == "door":
        # Door swing arc + door leaf
        draw.rectangle([2, target_h - 6, target_w - 3, target_h - 2], fill=stroke_col)
        draw.arc([2, 2, target_w * 2 - 4, target_h * 2 - 4], start=180, end=270, fill=stroke_col, width=2)
    elif kind == "dining_chair":
        draw.rounded_rectangle([2, 2, target_w - 3, target_h - 3], radius=3, fill=(235, 225, 210, 255), outline=stroke_col, width=2)
        draw.line([(2, int(target_h * 0.3)), (target_w - 3, int(target_h * 0.3))], fill=stroke_col, width=2)
    elif kind == "window":
        draw.rectangle([2, 2, target_w - 3, target_h - 3], fill=(224, 247, 250, 200), outline=(0, 229, 255, 255), width=2)
        draw.line([(2, target_h // 2), (target_w - 3, target_h // 2)], fill=(0, 229, 255, 255), width=1)
        draw.line([(2, 0), (2, target_h)], fill=(30, 41, 59, 255), width=2)
        draw.line([(target_w - 3, 0), (target_w - 3, target_h)], fill=(30, 41, 59, 255), width=2)
    else:
        draw.rectangle([2, 2, target_w - 3, target_h - 3], fill=fill_col, outline=stroke_col, width=2)

    return img


def get_furniture_image(item_id: str, target_w: int, target_h: int) -> Image.Image:
    """Get rasterized RGBA image for a furniture item, cached for speed."""
    key = (item_id, target_w, target_h)
    if key in _RASTER_CACHE:
        return _RASTER_CACHE[key]

    info = CLASS_BY_ITEM_ID.get(item_id)
    svg_file = SVG_DIR / (info.svg_name if info else f"{item_id}.svg")

    if svg_file.exists():
        img = render_svg_to_image(svg_file, target_w, target_h)
    elif info:
        img = render_procedural_furniture(info, target_w, target_h)
    else:
        img = Image.new("RGBA", (target_w, target_h), (220, 210, 195, 255))

    _RASTER_CACHE[key] = img
    return img
