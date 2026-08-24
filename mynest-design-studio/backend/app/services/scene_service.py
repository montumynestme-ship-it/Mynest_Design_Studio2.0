"""Canonical room-scene builder for the deterministic 3D renderer.

Composes the single source of truth the Three.js engine consumes: extracted walls
(world px) + furniture grouped into rooms, each with its bounding box and every
item's exact position/size/rotation. No AI decides any of these values
(CLAUDE.md RULE #1).
"""

from typing import Any

from app.data import furniture_catalog
from app.services import floor_plan_service, geometry_extraction_service, prompt_service


def _slug(label: str) -> str:
    return label.lower().replace(" & ", "-").replace(" ", "-")


def _room_bbox(items: list[dict[str, Any]]) -> list[float]:
    xs = [float(i["cx"]) for i in items]
    ys = [float(i["cy"]) for i in items]
    ws = [float(i["w"]) for i in items]
    hs = [float(i["h"]) for i in items]
    x0 = min(c - w / 2 for c, w in zip(xs, ws, strict=False))
    x1 = max(c + w / 2 for c, w in zip(xs, ws, strict=False))
    y0 = min(c - h / 2 for c, h in zip(ys, hs, strict=False))
    y1 = max(c + h / 2 for c, h in zip(ys, hs, strict=False))
    return [x0, y0, x1 - x0, y1 - y0]


def build_scene(file_id: str) -> dict[str, Any]:
    """Return {page, walls, rooms[]} — everything in world px (world = pdf_pt × scale)."""
    path, file_type, _ = floor_plan_service.get_floor_plan_file(file_id)
    canonical = floor_plan_service.get_canonical(file_id)
    furniture = canonical.get("furniture", []) or []

    walls: list[list[float]] = []
    wall_colors: list[str] = []
    page: dict[str, float] = {"width": 1000.0, "height": 750.0, "scale": 1.0}
    if file_type == "pdf":
        try:
            geometry = geometry_extraction_service.extract_walls(str(path))
            walls = geometry["walls"]
            wall_colors = geometry.get("wall_colors", [])
            page = geometry["page"]
        except Exception:  # noqa: BLE001 — a plan without vectors still renders furniture
            walls = []
            wall_colors = []

    # Drop detached annotation/detail blocks drawn *below* the inhabited plan
    # (legend, section detail, title strip). They are separated from the real
    # rooms by a clear vertical gap, so anything wholly below that gap is markup,
    # not architecture.
    if walls and furniture:
        fy0 = min(float(i["cy"]) - float(i["h"]) / 2 for i in furniture)
        fy1 = max(float(i["cy"]) + float(i["h"]) / 2 for i in furniture)
        tops_below = sorted(min(w[1], w[3]) for w in walls if min(w[1], w[3]) > fy1)
        if tops_below and (tops_below[0] - fy1) > max(40.0, (fy1 - fy0) * 0.03):
            cut = tops_below[0] - 1.0
            kept_w: list[list[float]] = []
            kept_c: list[str] = []
            for idx, w in enumerate(walls):
                if min(w[1], w[3]) < cut:
                    kept_w.append(w)
                    if idx < len(wall_colors):
                        kept_c.append(wall_colors[idx])
            walls = kept_w
            wall_colors = kept_c

    rooms: list[dict[str, Any]] = []
    groups = prompt_service.group_by_room(furniture)
    groups.sort(key=lambda g: len(g[1]), reverse=True)
    for label, items in groups:
        if not items:
            continue
        rooms.append(
            {
                "id": _slug(label),
                "label": label,
                "bbox": _room_bbox(items),
                "furniture": [
                    {
                        "uid": str(i["uid"]),
                        "item_id": str(i["item_id"]),
                        "name": furniture_catalog.describe(str(i["item_id"]))[0],
                        "cx": float(i["cx"]),
                        "cy": float(i["cy"]),
                        "w": float(i["w"]),
                        "h": float(i["h"]),
                        "rotation": float(i.get("rotation", 0)),
                    }
                    for i in items
                ],
            }
        )
    return {"page": page, "walls": walls, "wall_colors": wall_colors, "rooms": rooms}
