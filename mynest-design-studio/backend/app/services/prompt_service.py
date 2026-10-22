"""Server-side room-aware prompt synthesis with geometry-faithful constraint.

Groups the placed furniture into rooms and builds one geometry-faithful prompt
per room (PRD §28 Master AI Constraint injected server-side).
"""

import math
import re
from typing import Any

from app.data import furniture_catalog

MASTER_CONSTRAINT = """\
================================================================================
AUTHORITATIVE GEOMETRY & INVENTORY CONSTRAINT — NON-NEGOTIABLE
================================================================================

SOURCE OF TRUTH:
The supplied 2D floor plan / geometry reference is the AUTHORITATIVE source of
truth for this render. The generated image is a VISUALIZATION of the supplied design,
NOT a redesign. Never reinterpret, optimize, beautify, simplify, or redesign the spatial layout.

PRIORITY HIERARCHY:
1. Room geometry and architectural boundaries
2. Furniture inventory
3. Furniture geometry (position, orientation, scale)
4. Doors and windows
5. Spatial relationships
6. Camera
7. Style references
8. Visual variation
9. Creativity

FINAL PRIORITY ORDER:
LAYOUT & INVENTORY FIDELITY > ARCHITECTURAL FIDELITY > CAMERA > STYLE REFERENCE CONSISTENCY > CONTROLLED VARIATION > CREATIVITY.

STRICT INVENTORY (DO NOT BREAK):
- Render ONLY the furniture explicitly listed for this room.
- Do NOT omit any listed furniture.
- Do NOT add, move, remove, or rotate any furniture.
- Do NOT invent walls, windows, doors, or architectural features.
- Do NOT use a generic room layout.
- Render every listed furniture item exactly once unless its count explicitly says otherwise.
- Preserve the exact furniture count.

GEOMETRY — ABSOLUTELY FIXED:
- Preserve the exact room boundary and room shape from the authoritative reference.
- Preserve wall locations, wall lengths, wall angles, room proportions, and spatial relationships.
- Do NOT add, move, remove, or rotate any furniture.
- Do NOT invent walls, windows, doors, or architectural features.
- Do NOT use a generic room layout.
- Do NOT add, remove, move, resize, rotate, straighten, curve, or redesign walls.
- Do NOT change the room dimensions or aspect ratio.
- Do NOT expand or contract the room.
- Do NOT create architectural elements that are not present in the reference.
- Do NOT remove architectural elements that are present in the reference.

DOORS & WINDOWS — ABSOLUTELY FIXED:
- Preserve every door and window shown in the authoritative reference.
- Preserve their approximate position, orientation, size, and relationship to walls.
- Do NOT add, remove, relocate, enlarge, shrink, rotate, or redesign doors/windows.
- Preserve every door/window opening exactly as represented.
- Do NOT seal an existing opening or create a new opening.
- Do NOT invent balconies, arches, partitions, columns, niches, skylights, or openings.

FURNITURE GEOMETRY — ABSOLUTELY FIXED:
For every furniture item preserve:
- position
- orientation
- relative scale
- width/depth proportions
- relationship to walls
- relationship to other furniture
- clearance from walls and other objects

Do NOT move furniture.
Do NOT rotate furniture.
Do NOT resize furniture.
Do NOT mirror furniture.
Do NOT change furniture proportions.

The relative scale between furniture and room must remain physically believable and
consistent with the supplied geometry. A sofa must not become larger or smaller,
and a bed, table, chair, cabinet, or other item must not change its intended scale.

SPATIAL RELATIONSHIPS — FIXED:
- Preserve the exact spatial relationship between all listed furniture pieces.
- Preserve which furniture is adjacent to, opposite, aligned with, or separated from another furniture item.
- Preserve circulation spaces and clearances represented by the reference.
- Do NOT rearrange furniture to create a more aesthetically pleasing composition.
- Do NOT center furniture merely because it looks better.
- Do NOT symmetrize an asymmetric layout.
- Do NOT automatically align furniture to walls unless the reference already does so.

ROOM ISOLATION:
- Render ONLY the requested target room.
- Do NOT show any adjacent room, corridor, balcony, bathroom, kitchen, bedroom, living area, dining area, or other space outside the target room.
- Do NOT reveal adjacent rooms even partially through doors or openings.
- Do NOT borrow furniture or architectural elements from adjacent rooms.

REFERENCE IMAGE PRIORITY:
When a geometry/reference image is supplied:
- Treat it as authoritative for spatial structure.
- Follow the reference geometry rather than inventing geometry from textual description.
- Text descriptions explain the reference; they do not override the reference.
- Never use a generic room template when a reference is available.

CAMERA:
- Camera may change ONLY to produce a realistic photographic view of the existing geometry.
- Camera must not cause furniture, walls, doors, or windows to be repositioned.
- Do not use camera perspective to hide missing furniture or incorrect geometry.
- Do not crop out required furniture.
- Every required furniture item must remain visible whenever physically possible.
- Use natural architectural perspective with straight vertical lines.
- Avoid fisheye distortion, extreme wide-angle distortion, tilted horizons, or unrealistic perspective.

STYLE MAY CHANGE (VISUAL ONLY):
The following are allowed ONLY as visual treatment:
- materials
- textures
- finishes
- colors
- wood species
- stone appearance
- fabric appearance
- metal finishes
- wall treatment
- ceiling treatment
- realistic lighting
- shadows
- reflections
- exposure
- photographic quality

STYLE MUST NOT CHANGE:
- walls
- room dimensions
- doors
- windows
- openings
- furniture count
- furniture position
- furniture rotation
- furniture scale
- major architectural structure

CREATIVE FREEDOM — STRICTLY LIMITED:
Creativity is allowed only for making the existing design look photorealistic, premium, realistic, and professionally photographed.

FINAL VALIDATION BEFORE OUTPUT:
Before producing the final render, internally verify:
[ ] Correct room only
[ ] Correct room boundary
[ ] Correct walls
[ ] Correct doors
[ ] Correct windows
[ ] Correct furniture count
[ ] No extra furniture
[ ] No missing furniture
[ ] No furniture moved
[ ] No furniture rotated
[ ] No furniture resized
[ ] Correct spatial relationships
[ ] Correct furniture-to-room scale
[ ] No adjacent-room content
[ ] Camera does not hide or distort required geometry

If any of these conditions cannot be satisfied, prioritize GEOMETRY AND INVENTORY FIDELITY over visual creativity.

FINAL RULE:
LAYOUT & INVENTORY FIDELITY > ARCHITECTURAL FIDELITY > CAMERA > STYLE REFERENCE CONSISTENCY > CONTROLLED VARIATION > CREATIVITY.
================================================================================
"""


def _center(item: dict[str, Any]) -> tuple[float, float]:
    return float(item["cx"]), float(item["cy"])


def _dist(a: dict[str, Any], b: dict[str, Any]) -> float:
    ax, ay = _center(a)
    bx, by = _center(b)
    return math.hypot(ax - bx, ay - by)


def _centroid(items: list[dict[str, Any]]) -> tuple[float, float]:
    xs = [float(i["cx"]) for i in items]
    ys = [float(i["cy"]) for i in items]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def _style(design_intent: dict[str, Any] | None, canonical: dict[str, Any]) -> str | None:
    intent = design_intent or canonical.get("design_intent") or {}
    style = intent.get("style")
    return str(style) if style else None


# Room "anchors": one seed per real room. A bed = a bedroom, a sofa = a living
# room, a dining table = a kitchen/dining. Everything else is attached to the
# nearest compatible seed.
_SOFAS = {"sofa-3", "sofa-l", "lounger-sofa"}
_DINING_SEEDS = {"dining-table"}
# Kitchen appliances/units — one of these anchors a KITCHEN room, kept separate
# from the DINING room (which the dining table anchors).
_KITCHEN_IDS = {"kitchen-base", "cooktop", "sink", "refrigerator", "chimney"}
_SEED_IDS = furniture_catalog.BEDS | _SOFAS | _DINING_SEEDS
# Items that legitimately appear in several room types — assign purely by distance
# so a side table or window placed by the sofa joins the living room, not a far bedroom.
_GENERIC_IDS = {"side-table", "floor-lamp", "desk-lamp", "window", "door", "bay-window-seat"}
# Which seed kind each catalog room type belongs to.
_ROOM_TO_SEED_KIND = {
    "Bedroom": "bedroom",
    "Living Room": "living",
    "Dining Room": "dining",
    "Kitchen": "kitchen",
}

CANONICAL_SECTIONS = [
    "Living Area",
    "Kitchen",
    "Dining Area",
    "Bedroom 1",
    "Bedroom 2",
    "Bedroom 3",
]


def _seed_kind(item_id: str) -> str:
    if item_id in furniture_catalog.BEDS:
        return "bedroom"
    if item_id in _SOFAS:
        return "living"
    if item_id in _KITCHEN_IDS:
        return "kitchen"
    return "dining"


def _seed_size(f: dict[str, Any]) -> float:
    return max(float(f["w"]), float(f["h"]))


def _candidate_seeds(item: dict[str, Any], seeds: list[dict[str, Any]]) -> list[int]:
    """Seed indices this item may join — type-compatible ones, or all seeds for
    generic/uncovered items."""
    item_id = str(item["item_id"])
    if item_id in _GENERIC_IDS:
        return list(range(len(seeds)))
    _, room = furniture_catalog.describe(item_id)
    want = _ROOM_TO_SEED_KIND.get(room)
    if want is None:
        return list(range(len(seeds)))
    compatible = [i for i, s in enumerate(seeds) if _seed_kind(str(s["item_id"])) == want]
    return compatible or list(range(len(seeds)))


def _seed_label(items: list[dict[str, Any]]) -> str:
    ids = {str(f["item_id"]) for f in items}
    rooms = {furniture_catalog.describe(str(f["item_id"]))[1] for f in items}
    if ids & furniture_catalog.BEDS:
        return "Bedroom"
    if ids & _SOFAS:
        return "Living Area"
    if "Dining Room" in rooms or (ids & _DINING_SEEDS):
        return "Dining Area"
    if "Kitchen" in rooms or (ids & _KITCHEN_IDS):
        return "Kitchen"
    return "Room"


def _number_duplicates(
    labeled: list[tuple[str, list[dict[str, Any]]]],
) -> list[tuple[str, list[dict[str, Any]]]]:
    """Disambiguate repeated labels (e.g. 3 bedrooms) by position: top-to-bottom,
    then left-to-right."""
    counts: dict[str, int] = {}
    for lbl, _ in labeled:
        counts[lbl] = counts.get(lbl, 0) + 1
    dup = {lbl for lbl, c in counts.items() if c > 1}
    rank: dict[int, int] = {}
    for lbl in dup:
        members = [(idx, _centroid(items)) for idx, (lb, items) in enumerate(labeled) if lb == lbl]
        members.sort(key=lambda m: (m[1][1], m[1][0]))
        for order, (idx, _) in enumerate(members, start=1):
            rank[idx] = order
    result: list[tuple[str, list[dict[str, Any]]]] = []
    for idx, (lbl, items) in enumerate(labeled):
        if lbl == "Bedroom":
            # If single bedroom, label as Bedroom 1 for consistency with 3BHK naming
            order = rank.get(idx, 1)
            result.append((f"Bedroom {order}", items))
        elif lbl in dup:
            result.append((f"{lbl} {rank[idx]}", items))
        else:
            result.append((lbl, items))
    return result


def group_by_room(furniture: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    """Return [(room_label, items)] — one entry per physical room.

    Anchor-seeded assignment: each bed/sofa/dining-table seeds a room; every other
    item joins the nearest *type-compatible* seed (appliances -> the kitchen/dining
    seed, a TV -> the sofa, etc.), while generic items (side tables, lamps) go to the
    nearest seed of any kind. Split anchors (an L-sofa drawn as two rectangles) merge.
    This avoids catalog-type mistakes (a side table by the sofa is no longer forced
    into a bedroom) without relying on wall geometry, which is too gap-ridden here to
    segment rooms reliably.
    """
    # Room-tag annotations are not furniture — never cluster, count, or seed on them.
    furniture = furniture_catalog.strip_annotations(furniture)
    enriched = [
        {**f, "_name": furniture_catalog.describe(str(f["item_id"]))[0]} for f in furniture
    ]
    seeds = [f for f in enriched if str(f["item_id"]) in _SEED_IDS]
    # Promote the largest kitchen appliance to a seed so the KITCHEN forms its own
    # room, separate from the dining table's DINING room.
    kitchen_items = [f for f in enriched if str(f["item_id"]) in _KITCHEN_IDS]
    if kitchen_items:
        seeds.append(max(kitchen_items, key=_seed_size))
    if not seeds:
        return [("Interior", enriched)] if enriched else []

    # Merge adjacent seeds of the same item type (e.g. an L-sofa split in two).
    parent = list(range(len(seeds)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(len(seeds)):
        for j in range(i + 1, len(seeds)):
            id_i = str(seeds[i]["item_id"])
            id_j = str(seeds[j]["item_id"])
            # Beds and dining tables are distinct room anchors — never merge separate beds into one room
            if id_i in furniture_catalog.BEDS or id_j in furniture_catalog.BEDS:
                continue
            if id_i in _DINING_SEEDS or id_j in _DINING_SEEDS:
                continue
            # Sofas in living room seating proximity merge into a single Living Area
            if (id_i in _SOFAS and id_j in _SOFAS) or id_i == id_j:
                reach = max(0.8 * (_seed_size(seeds[i]) + _seed_size(seeds[j])), 450.0)
                if _dist(seeds[i], seeds[j]) < reach:
                    parent[find(i)] = find(j)

    buckets: dict[int, list[dict[str, Any]]] = {}
    for item in enriched:
        candidates = _candidate_seeds(item, seeds)
        nearest = min(candidates, key=lambda i: _dist(item, seeds[i]))
        buckets.setdefault(find(nearest), []).append(item)

    labeled = [(_seed_label(items), items) for items in buckets.values()]
    return _number_duplicates(labeled)


def tags_by_section(canonical: dict[str, Any]) -> dict[str, str]:
    """Map each user-placed room-tag annotation to the furniture section it sits in,
    returning ``{section_label: tag_name}`` (keyed by both the display label and its
    normalized form). The tag's custom name rides the existing ``label`` field; it is
    pure styling context and never changes furniture, geometry, or room assignment.

    A tag is assigned to the section whose furniture bounding box CONTAINS it, else to
    the nearest section by centroid. Tags with an empty name are ignored; if two tags
    fall in one section the last one wins. Designs without tags return ``{}``.
    """
    furniture = (canonical or {}).get("furniture", []) or []
    tags = [f for f in furniture if furniture_catalog.is_annotation(f.get("item_id"))]
    if not tags:
        return {}
    groups = group_by_room(furniture)  # already excludes annotations
    if not groups:
        return {}
    boxes: list[tuple[str, float, float, float, float, float, float]] = []
    for lbl, items in groups:
        xs = [float(i.get("cx", 0.0)) for i in items]
        ys = [float(i.get("cy", 0.0)) for i in items]
        if not xs:
            continue
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        boxes.append((lbl, x0, x1, y0, y1, (x0 + x1) / 2, (y0 + y1) / 2))
    out: dict[str, str] = {}
    for tag in tags:
        name = str(tag.get("label") or "").strip()
        if not name:
            continue
        tx, ty = float(tag.get("cx", 0.0)), float(tag.get("cy", 0.0))
        containing: str | None = None
        nearest: str | None = None
        nearest_d: float | None = None
        for lbl, x0, x1, y0, y1, cx, cy in boxes:
            if x0 <= tx <= x1 and y0 <= ty <= y1:
                containing = lbl
            d = (tx - cx) ** 2 + (ty - cy) ** 2
            if nearest_d is None or d < nearest_d:
                nearest_d, nearest = d, lbl
        chosen = containing or nearest
        if chosen:
            out[chosen] = name
            out[_normalize_section_name(chosen)] = name
    return out


def _position_phrase(item: dict[str, Any], bbox: tuple[float, float, float, float]) -> str:
    """Describe where an item sits inside its room's bounding box.

    The floor-plan Y axis grows downward, so the TOP of the plan is the far/back
    wall and the BOTTOM is the near/front of the room (nearest the camera).
    """
    minx, miny, maxx, maxy = bbox
    span_x = (maxx - minx) or 1.0
    span_y = (maxy - miny) or 1.0
    cx, cy = _center(item)
    fx = (cx - minx) / span_x
    fy = (cy - miny) / span_y

    horiz = "left" if fx < 0.34 else "right" if fx > 0.66 else "center"
    vert = "back" if fy < 0.34 else "front" if fy > 0.66 else "middle"

    if horiz == "center" and vert == "middle":
        return "in the center of the room"
    if vert == "middle":
        return f"along the {horiz} wall"
    if horiz == "center":
        return f"against the {vert} wall"
    return f"in the {vert}-{horiz} corner"


def _orientation(item: dict[str, Any]) -> str | None:
    rot = float(item.get("rotation", 0)) % 180
    if rot <= 5 or rot >= 175:
        return None  # axis-aligned — nothing to call out
    # Near 90° means the piece's long side runs the other way.
    if 60 <= rot <= 120:
        return "rotated 90° (long side running front-to-back)"
    # Any other real rotation angle from the source plan — state the exact
    # degree rather than a vague "angled" description.
    full_rot = float(item.get("rotation", 0)) % 360
    return f"rotated {full_rot:.0f}° from axis-aligned"


def _wall_placement(item: dict[str, Any], bbox: tuple[float, float, float, float]) -> str:
    """Determine which wall (North, South, East, West) an item is against or closest to."""
    minx, miny, maxx, maxy = bbox
    span_x = (maxx - minx) or 1.0
    span_y = (maxy - miny) or 1.0
    cx, cy = _center(item)
    fx = (cx - minx) / span_x
    fy = (cy - miny) / span_y

    d_north = fy
    d_south = 1.0 - fy
    d_west = fx
    d_east = 1.0 - fx

    walls = [
        ("North (back/far)", d_north),
        ("South (front/foreground)", d_south),
        ("West (left)", d_west),
        ("East (right)", d_east),
    ]
    return min(walls, key=lambda w: w[1])[0]


def _get_item_name(it: dict[str, Any]) -> str:
    if it.get("_name"):
        return str(it["_name"])
    if it.get("name"):
        return str(it["name"])
    item_id = str(it.get("item_id", ""))
    if item_id:
        desc = furniture_catalog.describe(item_id)
        if desc and desc[0]:
            return desc[0]
        return item_id.replace("-", " ").replace("_", " ").title()
    return "Furniture Item"


def _spatial_lines(
    items: list[dict[str, Any]],
    wall_info: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    """Per-item 'what is where' lines so the model reproduces the real layout.

    `wall_info` (uid -> {nearest_wall_id, distance_to_wall_mm, wall_relationship},
    from `architectural_service.enrich_furniture_relationships` against the
    plan's real extracted walls) adds an exact measured distance when it's
    actually known, instead of only the bbox-relative "against the wall" /
    "in the corner" phrase.
    """
    if not items:
        return []
    xs = [float(i["cx"]) for i in items]
    ys = [float(i["cy"]) for i in items]
    bbox = (min(xs), min(ys), max(xs), max(ys))

    lines: list[str] = []
    window_items = [
        it for it in items
        if str(it.get("item_id")) in ("window", "bay-window-seat")
        or "window" in _get_item_name(it).lower()
    ]

    for it in items:
        phrase = _position_phrase(it, bbox)
        orient = _orientation(it)
        suffix = f", {orient}" if orient else ""
        wall_clause = ""
        info = wall_info.get(str(it.get("uid", ""))) if wall_info else None
        if (
            info
            and info.get("nearest_wall_id")
            and info.get("wall_relationship") in ("adjacent", "attached")
        ):
            dist_mm = info.get("distance_to_wall_mm")
            if isinstance(dist_mm, int | float):
                wall_clause = f", measured {dist_mm:.0f}mm from wall {info['nearest_wall_id']}"
        lines.append(f"- {_get_item_name(it)}: {phrase}{suffix}{wall_clause}")

    for win in window_items:
        wall = _wall_placement(win, bbox)
        lines.append(
            f"- WINDOW SPECIFICATION: Architectural window positioned on the {wall} wall "
            "with tailored floor-to-ceiling sheer linen curtains, allowing diffuse natural daylight to illuminate the interior."
        )
        non_window = [
            i for i in items
            if i != win and str(i.get("item_id")) not in ("window", "bay-window-seat")
        ]
        if non_window:
            nearest = min(non_window, key=lambda o: _dist(o, win))
            lines.append(f"- The {_get_item_name(nearest)} is situated directly adjacent to / along the window wall.")

    return lines


def _appearance_lines(items: list[dict[str, Any]]) -> list[str]:
    """One 'what each piece looks like' line per distinct item type, so the
    text-to-image model renders recognizable objects, not generic guesses."""
    seen: set[str] = set()
    lines: list[str] = []
    for it in items:
        name = _get_item_name(it)
        if name in seen:
            continue
        seen.add(name)
        desc = furniture_catalog.describe_visual(str(it["item_id"]))
        if desc:
            lines.append(f"- {name}: {desc}")
    return lines


def _counted_furniture(items: list[dict[str, Any]]) -> str:
    """'2x Dining Chair, 1x Dining Table' — counts matter for fidelity."""
    counts: dict[str, int] = {}
    order: list[str] = []
    for i in items:
        name = _get_item_name(i)
        if name not in counts:
            order.append(name)
        counts[name] = counts.get(name, 0) + 1
    return ", ".join(f"{counts[n]}x {n}" for n in order)


def _room_windows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The window openings placed as furniture items in this room."""
    return [
        it for it in items
        if str(it.get("item_id")) in ("window", "bay-window-seat")
        or "window" in _get_item_name(it).lower()
    ]


def _room_has_window(
    items: list[dict[str, Any]], windows: list[dict[str, Any]] | None
) -> bool:
    """True if this room has a window — from the reconstructed opening list OR a
    window placed as a furniture item. Unifying both sources stops the prompt
    from simultaneously saying 'no window' (ROOM OPENINGS) and describing sheer
    curtains/daylight (style palette)."""
    return bool(windows) or bool(_room_windows(items))


def _window_wall(
    items: list[dict[str, Any]], bbox: tuple[float, float, float, float]
) -> str | None:
    """Which wall the room's (first) window sits on, or None if there's no
    window item — so the camera can keep an existing window in frame."""
    wins = _room_windows(items)
    return _wall_placement(wins[0], bbox) if wins else None


def _has_media_unit(items: list[dict[str, Any]]) -> bool:
    """A TV / media console actually placed in the room (never assume one)."""
    ids = {str(i.get("item_id", "")).lower() for i in items}
    return any(k in i for i in ids for k in ("console", "tv-unit", "tv_unit", "media"))


def _focal(room_label: str, items: list[dict[str, Any]] | None = None) -> str:
    """The wall/subject the camera should face, so the view angle suits the room.

    Only names a TV / media wall when a media unit is actually placed — otherwise
    the model invents a TV feature wall the plan never had.
    """
    label = room_label.lower()
    if "bedroom" in label:
        return "the bed and its upholstered headboard wall as the focal point"
    if "living" in label:
        if items is not None and not _has_media_unit(items):
            return "the sofa seating grouping against its feature wall as the focal point"
        return "the TV / media console wall, with the sofa in the foreground"
    if "kitchen" in label and "dining" in label:
        return "the kitchen cabinetry and countertops on one side and the dining set on the other"
    if "kitchen" in label:
        return "the kitchen cabinetry and countertops"
    if "dining" in label:
        return "the dining table and chairs as the focal point"
    if "bath" in label:
        return "the vanity and fittings"
    return "the main furniture grouping"


def _room_dims(items: list[dict[str, Any]]) -> tuple[int, int]:
    """Landscape interior-photo framing (matches how a room is actually photographed);
    a wider frame for open/wide rooms."""
    if not items:
        return 1216, 832
    xs = [float(i["cx"]) for i in items]
    ys = [float(i["cy"]) for i in items]
    span_x = (max(xs) - min(xs)) or 1.0
    span_y = (max(ys) - min(ys)) or 1.0
    if span_x / span_y >= 1.4:
        return 1344, 768  # wide, open-plan room
    return 1216, 832  # standard 3:2 interior photo


def _default_items_for_section(section: str) -> list[dict[str, Any]]:
    """Default furniture layout for canonical sections when not yet placed on canvas."""
    if section == "Living Area":
        return [
            {"item_id": "lounger-sofa", "cx": 500, "cy": 600, "w": 1900, "h": 900, "rotation": 0, "_name": "Loungers Sofa"},
            {"item_id": "center-table", "cx": 500, "cy": 450, "w": 1000, "h": 600, "rotation": 0, "_name": "Center Table"},
            {"item_id": "console", "cx": 500, "cy": 180, "w": 1100, "h": 350, "rotation": 0, "_name": "Console"},
            {"item_id": "window", "cx": 500, "cy": 850, "w": 1800, "h": 200, "rotation": 0, "_name": "Window"},
        ]
    if section == "Kitchen":
        return [
            {"item_id": "kitchen-base", "cx": 400, "cy": 300, "w": 2400, "h": 600, "rotation": 0, "_name": "Kitchen Base"},
            {"item_id": "chimney", "cx": 400, "cy": 220, "w": 900, "h": 500, "rotation": 0, "_name": "Chimney"},
            {"item_id": "window", "cx": 650, "cy": 150, "w": 1200, "h": 200, "rotation": 0, "_name": "Window"},
        ]
    if section == "Dining Area":
        return [
            {"item_id": "dining-table", "cx": 500, "cy": 500, "w": 1500, "h": 900, "rotation": 0, "_name": "Dining Table"},
            {"item_id": "dining-chair", "cx": 400, "cy": 400, "w": 450, "h": 500, "rotation": 0, "_name": "Dining Chair"},
            {"item_id": "dining-chair", "cx": 600, "cy": 400, "w": 450, "h": 500, "rotation": 0, "_name": "Dining Chair"},
            {"item_id": "dining-chair", "cx": 400, "cy": 600, "w": 450, "h": 500, "rotation": 0, "_name": "Dining Chair"},
            {"item_id": "dining-chair", "cx": 600, "cy": 600, "w": 450, "h": 500, "rotation": 0, "_name": "Dining Chair"},
            {"item_id": "window", "cx": 500, "cy": 200, "w": 1400, "h": 200, "rotation": 0, "_name": "Window"},
        ]
    if section == "Bedroom 1":
        return [
            {"item_id": "bed", "cx": 500, "cy": 350, "w": 1800, "h": 2000, "rotation": 0, "_name": "Bed"},
            {"item_id": "side-table", "cx": 300, "cy": 350, "w": 450, "h": 450, "rotation": 0, "_name": "Side Table"},
            {"item_id": "side-table", "cx": 700, "cy": 350, "w": 450, "h": 450, "rotation": 0, "_name": "Side Table"},
            {"item_id": "dressing-table", "cx": 220, "cy": 650, "w": 1200, "h": 600, "rotation": 0, "_name": "Dressing Table"},
            {"item_id": "window", "cx": 500, "cy": 800, "w": 1600, "h": 200, "rotation": 0, "_name": "Window"},
        ]
    if section == "Bedroom 2":
        return [
            {"item_id": "bed", "cx": 500, "cy": 350, "w": 1600, "h": 2000, "rotation": 0, "_name": "Bed"},
            {"item_id": "side-table", "cx": 320, "cy": 350, "w": 450, "h": 450, "rotation": 0, "_name": "Side Table"},
            {"item_id": "side-table", "cx": 680, "cy": 350, "w": 450, "h": 450, "rotation": 0, "_name": "Side Table"},
            {"item_id": "window", "cx": 500, "cy": 800, "w": 1400, "h": 200, "rotation": 0, "_name": "Window"},
        ]
    if section == "Bedroom 3":
        return [
            {"item_id": "bed", "cx": 500, "cy": 350, "w": 1200, "h": 2000, "rotation": 0, "_name": "Bed"},
            {"item_id": "side-table", "cx": 350, "cy": 350, "w": 450, "h": 450, "rotation": 0, "_name": "Side Table"},
            {"item_id": "console", "cx": 250, "cy": 650, "w": 1100, "h": 350, "rotation": 0, "_name": "Console"},
            {"item_id": "window", "cx": 500, "cy": 800, "w": 1200, "h": 200, "rotation": 0, "_name": "Window"},
        ]
    return []


def _normalize_section_name(name: str) -> str:
    n = name.strip()
    nl = n.lower()
    if "living" in nl:
        return "Living Area"
    if "kitchen" in nl:
        return "Kitchen"
    if "dining" in nl:
        return "Dining Area"
    if "bedroom 1" in nl or nl == "bedroom":
        return "Bedroom 1"
    if "bedroom 2" in nl:
        return "Bedroom 2"
    if "bedroom 3" in nl:
        return "Bedroom 3"
    return n


def _deterministic_camera(
    room_label: str,
    items: list[dict[str, Any]],
    bbox: tuple[float, float, float, float],
    doors: list[dict[str, Any]] | None = None,
    windows: list[dict[str, Any]] | None = None,
) -> str:
    """Generate a camera viewpoint grounded in the deterministic room geometry (Section 8).

    - Exists inside or near the actual room perimeter/entrance
    - Produces a physically plausible perspective view
    - Faces the primary architectural focal point of the room
    - Shows important furniture in true geometric relationship
    - Keeps a window that the plan DOES have in frame, and forbids inventing one
      when the plan has NONE (the exact kitchen/bedroom mismatches reported)
    - Never uses one generic camera prompt for every room
    """
    label = room_label.lower()
    minx, miny, maxx, maxy = bbox
    span_x = (maxx - minx) or 1.0
    span_y = (maxy - miny) or 1.0

    door_wall = "entrance threshold"
    if doors:
        d = doors[0]
        dx, dy = float(d.get("x", minx)), float(d.get("y", maxy))
        fx = (dx - minx) / span_x
        fy = (dy - miny) / span_y
        if fy > 0.6:
            door_wall = "South (front) entrance threshold"
        elif fy < 0.4:
            door_wall = "North entrance threshold"
        elif fx < 0.4:
            door_wall = "West entry doorway"
        else:
            door_wall = "East entry doorway"

    ids = {str(i.get("item_id", "")).lower() for i in items}
    has_window = _room_has_window(items, windows)
    win_wall = _window_wall(items, bbox)

    # Window framing directive shared by every room type: if the plan HAS a
    # window, the camera must keep it in view (so an existing window is never
    # dropped); if it has NONE, no window/glazing may be invented.
    if has_window:
        wall_txt = f" on the {win_wall} wall" if win_wall else ""
        window_directive = (
            f" Frame the shot so the existing window{wall_txt} stays visible "
            "in view — angle the camera to include that window wall; do not crop it out."
        )
    else:
        window_directive = (
            " This room has NO window — render no window, glazing, glass wall, "
            "sliding glass door, skylight, or exterior view on any wall."
        )

    if "bedroom" in label:
        beds = [i for i in items if "bed" in str(i.get("item_id", "")).lower()]
        bed_wall = _wall_placement(beds[0], bbox) if beds else "North wall"
        # Only name furniture that's actually present — previously every
        # bedroom claimed "flanking nightstands, and adjoining wardrobe"
        # even when no such items were placed.
        feature_bits = ["the upholstered headboard"]
        if any("side-table" in i for i in ids):
            feature_bits.append("flanking nightstands")
        if any("wardrobe" in i for i in ids):
            feature_bits.append("adjoining wardrobe")
        features = ", ".join(feature_bits)
        return (
            "DETERMINISTIC CAMERA VIEWPOINT: Camera positioned at standing eye level "
            f"(1.5m height) at the {door_wall}, angled diagonally across the room "
            f"toward the {bed_wall} feature wall showcasing {features}. "
            "32mm architectural wide-angle lens, natural two-point perspective, "
            "strictly horizontal camera plane with straight vertical walls "
            f"(no tilt or fisheye), entire room in frame.{window_directive}"
        )
    if "living" in label:
        foreground_bits = []
        if any("sofa" in i for i in ids):
            foreground_bits.append("the sofa")
        if any("center-table" in i or "coffee-table" in i for i in ids):
            foreground_bits.append("center table")
        foreground = " and ".join(foreground_bits) if foreground_bits else "the seating grouping"
        # Only aim at a media wall when a media unit is actually placed.
        focal_wall = (
            "the focal TV / media console wall"
            if _has_media_unit(items)
            else "the focal feature wall behind the seating"
        )
        return (
            "DETERMINISTIC CAMERA VIEWPOINT: Camera positioned at standing eye level "
            f"(1.5m height) at the {door_wall}, looking diagonally across the main "
            f"seating grouping toward {focal_wall} with {foreground} "
            f"in the foreground. 30mm architectural wide-angle lens, "
            "natural two-point perspective, strictly vertical walls (no tilt or "
            f"fisheye), preserving exact floor-plan spatial relationships.{window_directive}"
        )
    if "kitchen" in label:
        return (
            "DETERMINISTIC CAMERA VIEWPOINT: Camera positioned at standing eye level (1.5m height) at the kitchen entrance, "
            "oriented along the primary counter run looking toward the cooktop, overhead chimney, and clean countertop workspace. "
            f"30mm architectural lens, natural two-point perspective, straight vertical lines without distortion.{window_directive}"
        )
    if "dining" in label:
        dining_window = (
            " toward the architectural feature wall and window" if has_window
            else " toward the architectural feature wall"
        )
        return (
            "DETERMINISTIC CAMERA VIEWPOINT: Camera positioned at standing eye level (1.5m height) at the edge of the dining zone, "
            f"oriented across the dining table and chairs{dining_window}. "
            f"32mm architectural lens, natural two-point perspective with straight verticals and surrounding clearance visible.{window_directive}"
        )
    return (
        f"DETERMINISTIC CAMERA VIEWPOINT: Camera positioned at standing eye level (1.5m height) at the {door_wall}, "
        f"looking across the room toward {_focal(room_label, items)}. 32mm lens, natural two-point perspective, straight vertical walls.{window_directive}"
    )


def _room_dimensions_description(
    items: list[dict[str, Any]],
    bbox: tuple[float, float, float, float],
    mpp: float = 0.01,
    dims_meta: dict[str, Any] | None = None,
    geom_source: str | None = None,
) -> str:
    # Prefer the authoritative architectural dimensions (from reconstructed
    # wall polygons) over a bbox-span estimate whenever they're available —
    # and say so honestly either way, instead of always claiming "EXACT".
    if dims_meta and geom_source == "architectural":
        w_m = dims_meta.get("width_m")
        d_m = dims_meta.get("depth_m")
        area = dims_meta.get("area_sqm")
        if w_m and d_m:
            return (
                f"EXACT ROOM DIMENSIONS & PROPORTIONS (from the reconstructed architectural "
                f"boundary): {w_m}m width × {d_m}m depth × 2.7m ceiling height ({area} m²). "
                "The room's boundaries, aspect ratio, and proportions are STRICTLY DETERMINED "
                "by the 2D floor plan's actual walls."
            )

    minx, miny, maxx, maxy = bbox
    span_x = maxx - minx
    span_y = maxy - miny
    w_m = round(span_x * mpp, 1) if span_x > 0 else 4.2
    d_m = round(span_y * mpp, 1) if span_y > 0 else 3.8
    w_m = max(2.4, min(14.0, w_m))
    d_m = max(2.4, min(14.0, d_m))
    area = round(w_m * d_m, 1)
    return (
        f"APPROXIMATE ROOM DIMENSIONS & PROPORTIONS (estimated from furniture placement — "
        f"no closed architectural boundary available): {w_m}m width × {d_m}m depth × 2.7m "
        f"ceiling height ({area} m²). Treat the furniture layout below, not this estimate, as "
        "the authoritative boundary — do not redesign or expand the room."
    )


def _room_specific_guidance(room_label: str, items: list[dict[str, Any]]) -> list[str]:
    """Room-type guidance naming only items actually present in `items`.

    The previous version named a fixed checklist (sofa/coffee-table/TV for
    every living room, wardrobe/dressing-unit for every bedroom, ...)
    regardless of whether the room actually has one — contradicting the
    STRICT INVENTORY rule for any room missing one of those items.
    """
    label = room_label.lower()
    ids = {str(i.get("item_id", "")).lower() for i in items}

    def _has(*needles: str) -> bool:
        return any(any(n in item_id for n in needles) for item_id in ids)

    guidance: list[str] = []
    if "living" in label:
        present = []
        if _has("sofa"):
            present.append("the exact sofa seating configuration")
        if _has("center-table", "coffee-table"):
            present.append("center/coffee table placement")
        if _has("console", "tv-unit"):
            present.append("TV media console alignment")
        if present:
            guidance.append(
                f"LIVING AREA SPECIFICATION: Strictly preserve {', '.join(present)}. "
                "Do not generate a generic living room or add furniture not listed below."
            )
        else:
            guidance.append(
                "LIVING AREA SPECIFICATION: Strictly preserve exactly the furniture listed "
                "below, in its exact layout. Do not generate a generic living room."
            )
    elif "kitchen" in label:
        present = []
        if _has("kitchen-base"):
            present.append("the exact kitchen counter run and base cabinets")
        if _has("cooktop"):
            present.append("cooktop")
        if _has("chimney"):
            present.append("overhead chimney")
        if _has("sink"):
            present.append("sink")
        if _has("refrigerator"):
            present.append("refrigerator")
        if present:
            guidance.append(
                f"KITCHEN SPECIFICATION: Strictly preserve {', '.join(present)}, exactly as shown. "
                "Do not invent an arbitrary kitchen shape or add appliances not listed below."
            )
        else:
            guidance.append(
                "KITCHEN SPECIFICATION: Strictly preserve exactly the furniture listed below. "
                "Do not invent an arbitrary kitchen shape or add appliances not listed."
            )
    elif "dining" in label:
        if _has("dining-table", "dining-chair"):
            guidance.append(
                "DINING AREA SPECIFICATION: Strictly preserve the exact dining table, chair count, "
                "table orientation, and surrounding circulation clearance. Do not replace with a "
                "generic dining room or add extra chairs/tables not listed below."
            )
        else:
            guidance.append(
                "DINING AREA SPECIFICATION: Strictly preserve exactly the furniture listed below. "
                "Do not replace with a generic dining room."
            )
    elif "bedroom" in label:
        present = []
        if _has("bed"):
            present.append("the bed dimensions and orientation")
        if _has("side-table"):
            present.append("nightstand placement")
        if _has("wardrobe"):
            present.append("wardrobe placement")
        if _has("dressing-table"):
            present.append("dressing unit placement")
        if present:
            guidance.append(
                f"BEDROOM SPECIFICATION: Strictly preserve {', '.join(present)} as specified — "
                "only the items actually listed below. Do not substitute a generic bedroom "
                "template or add furniture that isn't listed."
            )
        else:
            guidance.append(
                "BEDROOM SPECIFICATION: Strictly preserve exactly the furniture listed below. "
                "Do not substitute a generic bedroom template."
            )
    return guidance


def _room_style_profile(
    room_label: str,
    intent: dict[str, Any],
    seed: int | None = None,
    room_index: int = 1,
    has_window: bool = True,
) -> list[str]:
    """Dynamic per-category / per-index material & lighting palette.

    Living/Kitchen/Dining get a fixed premium palette (with seed-driven
    micro-variation for visual diversity across regenerations). Bedrooms cycle
    deterministically through three distinct palettes by bedroom number via
    ``(room_index - 1) % 3`` — so no two adjacent bedrooms share the same grey
    walls / white bed (current issue #3). Unknown/custom room labels fall back
    to a modern Indian executive residential finish.

    This governs ONLY materials, finishes and lighting — never geometry,
    furniture, or openings (those are locked upstream).
    """
    label = room_label.lower()
    variation_idx = (seed % 4) if seed is not None else 0

    # Curtains/daylight only when the room truly has a window — otherwise the
    # palette contradicts the ROOM OPENINGS constraint and the model paints a
    # phantom window (the reported kitchen/windowless-room failure).
    curtains = (
        "floor-to-ceiling sheer linen curtains diffusing soft daylight"
        if has_window
        else "soft layered warm interior lighting only (this room has no window — "
        "no curtains, glazing, or exterior daylight)"
    )

    parts: list[str] = []

    if "living" in label:
        wood_variations = [
            "vertical fluted natural oak/walnut wood slat panels with subtle champagne bronze metal inlay trims",
            "rift-cut smoked oak timber paneling with warm concealed architectural backlighting",
            "warm natural walnut slat feature wall with recessed bronze metal reveal trims",
            "fluted natural white oak wood slat panels paired with minimalist bronze accent detailing",
        ]
        stone_variations = [
            "smooth Statuario porcelain marble slab accenting",
            "honed Calacatta gold marble slab feature paneling",
            "seamless bookmatched Italian marble wall accents",
            "veined travertine stone slab feature wall accenting",
        ]
        wood_choice = wood_variations[variation_idx]
        stone_choice = stone_variations[variation_idx]

        parts.append(
            "MATERIAL & LIGHTING PALETTE — Refined contemporary luxury living area: "
            "layered gypsum false ceiling with warm concealed 3000K LED cove strip lighting plus "
            "anti-glare recessed architectural spotlights casting soft ambient illumination."
        )
        parts.append(
            f"WALL & FLOOR FINISHES: rich walnut paneling feature wall ({wood_choice}), "
            f"paired with {stone_choice}, over warm travertine / large-format polished stone flooring."
        )
        parts.append(
            "TEXTILES: warm beige linen upholstery, curated greige, alabaster, soft taupe and brushed "
            f"brass palette, with {curtains}."
        )

    elif "kitchen" in label:
        cab_finishes = [
            "seamless handleless flat-panel cabinetry in warm cream matte lacquer with natural oak accents",
            "warm cream and natural oak flat-panel cabinetry with soft matte lacquer uppers",
            "minimalist warm ivory cabinetry with light natural oak base units and champagne brass pulls",
            "warm beige and honey-oak flat-panel cabinetry with integrated champagne brass finger pulls",
        ]
        parts.append(
            "MATERIAL & LIGHTING PALETTE — Warm modern-luxury kitchen (bright, airy, not dark): flush "
            "architectural ceiling with recessed anti-glare downlights and continuous warm 3000K "
            "under-cabinet LED task strip lighting."
        )
        parts.append(
            f"CABINETRY & COUNTERTOPS: {cab_finishes[variation_idx]}, Calacatta white marble countertops "
            "and full-height matching marble slab backsplash in warm neutral tones."
        )
        parts.append(
            "APPLIANCES & FIXTURES: integrated cooktop with overhead architectural chimney hood, undermount "
            "sink with champagne-brass gooseneck faucet, warm honey-oak plank or light porcelain flooring."
        )

    elif "dining" in label:
        pendant_styles = [
            "sculptural contemporary linear pendant in champagne brass centered over the dining table",
            "minimalist circular brass halo pendant casting warm ambient illumination over the table",
            "trio of smoked-glass and bronze pendant lights suspended at staggered heights over the table",
            "horizontal brass beam pendant fixture with diffused warm LED glow over the table",
        ]
        parts.append(
            f"MATERIAL & LIGHTING PALETTE — Elegant contemporary dining area: concealed perimeter ceiling "
            f"cove with warm 2700K ambient light plus direct pendant lighting — a {pendant_styles[variation_idx]}."
        )
        parts.append(
            "WALL & FLOOR FINISHES: warm natural stone accent wall with fluted oak slat paneling and a "
            "recessed warm-backlit niche, over large-format porcelain flooring with a subtle sheen."
        )
        parts.append(
            "TABLE & CHAIR FINISHES: solid walnut dining table with a refined beveled edge, paired with "
            "upholstered dining chairs in textured bouclé and tailored linen on matte metal legs."
        )

    elif "bedroom" in label:
        # Cycle three distinct bedroom palettes by bedroom NUMBER so adjacent
        # bedrooms never look identical (issue #3). Bedroom 1 -> A, 2 -> B,
        # 3 -> C, 4 -> A, ... via (index - 1) % 3.
        palette = (max(1, room_index) - 1) % 3
        if palette == 0:
            # Palette A — warm walnut
            parts.append(
                "MATERIAL & LIGHTING PALETTE — Bedroom Palette A (warm walnut): perimeter recessed cove "
                "ceiling with soft indirect warm 2700K headboard LED and reading sconces flanking the bed."
            )
            parts.append(
                "FEATURE HEADBOARD WALL: warm walnut headboard with vertical fluted oak paneling and subtle "
                "champagne bronze reveals."
            )
            parts.append(
                "TEXTILES & FLOOR: plush neutral beige carpet underfoot, crisp cotton and waffle-linen "
                f"bedding, {curtains}."
            )
        elif palette == 1:
            # Palette B — light natural ash. Bright morning daylight only when the
            # room actually has a window; otherwise warm concealed cove lighting.
            b_light = (
                "airy ceiling with bright soft morning daylight supplemented by warm concealed cove lighting"
                if has_window
                else "airy ceiling with soft warm concealed cove lighting and recessed downlights (no window daylight)"
            )
            parts.append(
                f"MATERIAL & LIGHTING PALETTE — Bedroom Palette B (light natural ash): {b_light}."
            )
            parts.append(
                "FEATURE HEADBOARD WALL: light natural ash wood headboard against smooth cream plaster walls."
            )
            parts.append(
                "TEXTILES & FLOOR: light oak plank flooring, soft neutral bouclé and sage accents, "
                f"{curtains}."
            )
        else:
            # Palette C — warm charcoal + walnut, cozy evening ambiance (moody
            # but warm-toned, not cold industrial grey).
            parts.append(
                "MATERIAL & LIGHTING PALETTE — Bedroom Palette C (charcoal evening): cozy warm evening "
                "ambiance from concealed 2700K cove lighting and minimalist linear wall sconces with a "
                "warm amber glow."
            )
            parts.append(
                "FEATURE HEADBOARD WALL: warm charcoal accent wall with warm smoked walnut slat detailing "
                "and integrated floating bedside ledges with warm halo backlighting."
            )
            parts.append(
                "TEXTILES & FLOOR: plush warm-taupe rug, tailored warm taupe and greige linen bedding, "
                f"brushed bronze hardware, warm oak plank flooring, {curtains}."
            )

    else:
        # Unknown / custom dynamic room label — modern Indian executive fallback.
        parts.append(
            "MATERIAL & LIGHTING PALETTE — Modern Indian executive residential finish: clean recessed "
            "ceiling with warm concealed 3000K LED cove strip lighting and soft ambient daylight."
        )
        parts.append(
            "WALL & FLOOR FINISHES: refined feature wall with warm wood slat panels and textured acoustic "
            "fabric inserts, over large-format polished porcelain flooring."
        )
        parts.append(
            f"TEXTILES: warm neutral palette with linen and bouclé textiles and {curtains}."
        )

    return parts


def _room_negatives(
    room_label: str,
    items: list[dict[str, Any]],
    has_window: bool = True,
) -> list[str]:
    """Concise, room-specific anti-hallucination clauses that MUST reach the
    text-to-image model (front-loaded, since the Flux condenser strips the
    MASTER_CONSTRAINT and the "This is STRICTLY" line).

    These target the exact failure modes seen in real renders: the kitchen
    growing a central island, the dining area turning into a full kitchen, a
    windowless room sprouting a phantom window, and rooms sprouting furniture
    that isn't in the plan. Every clause is geometry-honest — it only forbids
    things that are provably not in the authoritative furniture/opening list.
    """
    label = room_label.lower()
    ids = {str(i.get("item_id", "")).lower() for i in items}

    def _has(*needles: str) -> bool:
        return any(any(n in i for n in needles) for i in ids)

    lines: list[str] = [
        f"STRICT ROOM ISOLATION: render only this {label}; do NOT show or bleed in any "
        "other room, hallway, corridor, or adjacent space, and do NOT view another room "
        "through a doorway."
    ]

    if "kitchen" in label:
        lines.append(
            "KITCHEN LAYOUT LOCK: the cabinets and countertops run ALONG THE PERIMETER "
            "WALLS following the exact plan footprint (galley / L-shaped wall run). "
            "Absolutely NO central kitchen island, NO peninsula, and NO free-standing "
            "counter block — none exist in the plan. Do NOT add a dining table or chairs."
        )
    elif "dining" in label:
        # A dining area must never render as a kitchen.
        lines.append(
            "DINING-ONLY LOCK: this is a dining area, NOT a kitchen. Do NOT render any "
            "kitchen, kitchen cabinetry, countertops, cooktop, chimney, hood, sink, or "
            "refrigerator. Show only the dining furniture listed above."
        )
    elif "living" in label:
        lines.append(
            "LIVING-AREA LOCK: do NOT add extra sofas, armchairs, ottomans, a TV / media "
            "unit, or a coffee/center table beyond those explicitly listed above."
        )
    elif "bedroom" in label:
        forbidden = []
        if not _has("wardrobe"):
            forbidden.append("wardrobe")
        if not _has("dressing"):
            forbidden.append("dressing table")
        if not _has("side-table"):
            forbidden.append("nightstand")
        if not _has("console", "chest", "dresser"):
            forbidden.append("dresser/chest of drawers")
        if forbidden:
            lines.append(
                "BEDROOM FURNITURE LOCK: do NOT add a " + ", ".join(forbidden)
                + " — none are in this room's plan. Render only the furniture listed above."
            )
        else:
            lines.append(
                "BEDROOM FURNITURE LOCK: render only the furniture listed above; add no "
                "extra storage or seating."
            )

    # Windowless lock — the plan has no window on any wall, so the model must not
    # invent one (fixes the kitchen render showing a window the 2D plan never had).
    # Emitted after the room-type lock so both survive the Flux condenser, and
    # front of the whole prompt so it isn't truncated away.
    if not has_window:
        lines.append(
            "WINDOWLESS ROOM: NO window in the plan — do NOT render any window, glazing, "
            "glass wall, sliding glass door, skylight, or exterior view on any wall; use "
            "warm interior cove/recessed lighting only against solid walls."
        )

    return lines


def _room_prompt(
    room_label: str,
    items: list[dict[str, Any]],
    design_intent: dict[str, Any] | None,
    bbox: tuple[float, float, float, float] | None = None,
    doors: list[dict[str, Any]] | None = None,
    windows: list[dict[str, Any]] | None = None,
    seed: int | None = None,
    dims_meta: dict[str, Any] | None = None,
    geom_source: str | None = None,
    wall_info: dict[str, dict[str, Any]] | None = None,
    room_index: int = 1,
) -> str:
    intent = design_intent or {}
    style_val = intent.get("style") or "Modern Luxury"

    if bbox is None:
        if items:
            xs = [float(i["cx"]) for i in items]
            ys = [float(i["cy"]) for i in items]
            bbox = (min(xs), min(ys), max(xs), max(ys))
        else:
            bbox = (0.0, 0.0, 1000.0, 1000.0)

    # A window exists if the reconstruction found one OR one was placed as a
    # furniture item — unify both so ROOM OPENINGS, the style palette, and the
    # camera never contradict each other (phantom windows / dropped windows).
    has_window = _room_has_window(items, windows)
    n_windows_effective = len(windows or []) or len(_room_windows(items))

    camera_spec = _deterministic_camera(room_label, items, bbox, doors, windows)
    dims_spec = _room_dimensions_description(
        items, bbox, dims_meta=dims_meta, geom_source=geom_source,
    )
    room_rules = _room_specific_guidance(room_label, items)

    parts: list[str] = []

    # 1. PRIMARY INVENTORY FIRST. The downstream Flux condenser truncates the
    # prompt body, and text-to-image weights early tokens most heavily, so the
    # exact furniture inventory must lead — otherwise the core items get buried
    # under camera/material text and dropped (e.g. a dining room rendered as an
    # empty hallway). Never invent or omit items.
    if items:
        inventory = _counted_furniture(items)
        parts.append(
            f"Photorealistic architectural interior photograph of a {room_label.lower()} "
            f"that contains exactly: {inventory}. Render every one of these items and nothing "
            "else — no extra, duplicate, missing, or invented furniture or decor."
        )
    else:
        parts.append(
            f"Photorealistic architectural interior photograph of a {room_label.lower()}."
        )
    # Room-specific negatives / isolation — placed HERE (near the front, and NOT
    # starting with "This is STRICTLY") so it survives the Flux condenser, which
    # both truncates the tail AND strips the MASTER_CONSTRAINT block and any line
    # starting with "This is STRICTLY". Without this, the model never receives the
    # anti-hallucination rules and e.g. grows a kitchen island or turns a dining
    # area into a full kitchen.
    parts.extend(_room_negatives(room_label, items, has_window=has_window))
    # Redundant isolation line kept for non-Flux adapters (stripped by the condenser).
    parts.append(
        f"This is STRICTLY a {room_label.lower()} — render only this one room and only "
        "the furniture listed; ignore every other room."
    )

    if items:
        appearance = _appearance_lines(items)
        if appearance:
            parts.append(
                "PIECE APPEARANCE (render each piece true to its real-world type; "
                "apply the chosen style/materials as its finish):"
            )
            parts.extend(appearance)
        spatial = _spatial_lines(items, wall_info=wall_info)
        if spatial:
            parts.append(
                "SPATIAL LAYOUT (authoritative — reproduce these relative positions and "
                "rotations exactly; the front of the room is nearest the camera):"
            )
            parts.extend(spatial)

    # 2. ROOM-SPECIFIC OPENINGS & BOUNDARIES (never the whole plan's openings).
    n_doors = len(doors or [])
    if not has_window:
        parts.append(
            f"ROOM OPENINGS: this room has {n_doors} door(s) and no exterior window — "
            "illuminate with warm ambient interior lighting (cove + recessed downlights), "
            "not window daylight. Do not add, remove, or invent any opening."
        )
    else:
        win_wall = _window_wall(items, bbox)
        wall_txt = f" (window on the {win_wall} wall)" if win_wall else ""
        parts.append(
            f"ROOM OPENINGS: preserve exactly this room's {n_doors} door(s) and "
            f"{n_windows_effective} window(s){wall_txt} in their given positions, and keep "
            "the window visible in the framed view; do not add, remove, relocate, resize, "
            "or borrow another room's openings."
        )
    parts.append(dims_spec)
    parts.extend(room_rules)

    # 3. CAMERA.
    parts.append(
        f"Architectural interior photograph of the {room_label.lower()} in high-end "
        f"{style_val} style. Camera at standing eye level (1.5m height) at the room's "
        f"entrance/doorway, facing the room's central axis toward {_focal(room_label, items)}. "
        "Natural 35mm perspective, straight vertical walls, no fisheye or wide-angle "
        "distortion, the whole room in frame with every listed piece visible in its "
        "correct relative position."
    )
    parts.append(camera_spec)

    # 4. DYNAMIC MATERIAL & LIGHTING PALETTE (lowest priority — style, not geometry).
    parts.append(
        "AESTHETIC DIRECTION: sophisticated modern Indian urban-home interior — contemporary "
        "luxury residential design, professional architectural-interior photography, "
        "photorealistic and not CGI-looking. This governs materials/lighting/finish only, "
        "never the room's geometry or furniture placement above."
    )
    parts.extend(
        _room_style_profile(
            room_label, intent, seed=seed, room_index=room_index, has_window=has_window
        )
    )

    if intent.get("style"):
        parts.append(f"STYLE: {intent['style']}.")
    if intent.get("mood"):
        parts.append(f"MOOD: {intent['mood']}.")
    # User-written theme (free text from the AI Render dialog) — a styling directive
    # placed HERE with STYLE/MOOD (near the front) so it survives the Flux condenser
    # that truncates the tail. Sanitised to one line and length-capped; styling only.
    theme_txt = " ".join(str(intent.get("theme") or "").split())[:1200]
    if theme_txt:
        parts.append(f"USER THEME (styling only): {theme_txt}")
        parts.append(
            "Apply this ONLY to materials, colours, textures, lighting, mood and decor. "
            "It does NOT permit adding, removing, moving, resizing or re-typing any "
            "furniture, walls, doors or windows — the exact layout is authoritative."
        )
    if intent.get("colors"):
        parts.append("COLOR PALETTE: " + ", ".join(intent["colors"]) + ".")
    if intent.get("materials"):
        parts.append("MATERIALS: " + ", ".join(intent["materials"]) + ".")
    if intent.get("lighting"):
        parts.append(f"LIGHTING: {intent['lighting']}.")

    parts.append("")
    parts.append(MASTER_CONSTRAINT)
    return "\n".join(parts)


def build_locked_prompt(
    canonical: dict[str, Any], design_intent: dict[str, Any] | None
) -> str:
    """Prompt for the geometry-locked ControlNet render (Phase C, top-down).

    The canny control map carries the authoritative geometry; this prompt only
    steers materials/lighting and forbids the model from altering the layout.
    """
    intent = design_intent or canonical.get("design_intent") or {}
    style = _style(design_intent, canonical)
    parts = [
        "Top-down architectural 3D dollhouse visualization of this residential floor "
        "plan, photorealistic materials, textures, flooring, and soft interior lighting.",
        "The outlined shapes are FIXED walls and furniture footprints: reproduce every "
        "wall and every furniture piece at exactly the same position, size, and "
        "orientation as shown.",
    ]
    if style:
        parts.append(f"STYLE: {style}.")
    if intent.get("colors"):
        parts.append("COLOR PALETTE: " + ", ".join(intent["colors"]) + ".")
    if intent.get("materials"):
        parts.append("MATERIALS: " + ", ".join(intent["materials"]) + ".")
    parts.append(
        "Do NOT add, move, remove, rotate, or resize any wall or furniture. Only apply "
        "realistic materials, textures, and lighting to the existing layout."
    )
    return " ".join(parts)


def get_eligible_sections(canonical: dict[str, Any]) -> list[str]:
    """Derive eligible renderable sections from the authoritative floor plan (Phases 2 & 3).

    No hard-coded 6 rooms: returns the exact room sections present in the design.
    """
    furniture = canonical.get("furniture", []) or []
    placed_groups = group_by_room(furniture) if furniture else []
    if placed_groups:
        def section_sort_key(label: str) -> tuple[int, int | str]:
            l = label.lower()
            if "living" in l:
                return (0, 0)
            if "kitchen" in l:
                return (1, 0)
            if "dining" in l:
                return (2, 0)
            if "bedroom" in l:
                parts = label.split()
                num = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
                return (3, num)
            return (4, label)

        sections = [lbl for lbl, items in placed_groups if items]
        sections.sort(key=section_sort_key)
        return sections

    # Fallback to architectural reconstruction if walls exist
    walls = canonical.get("structured_walls") or canonical.get("walls") or []
    if walls:
        try:
            from app.services import architectural_service
            reconstructed = architectural_service.reconstruct_rooms([], walls)
            if reconstructed:
                return [r["label"] for r in reconstructed if r.get("label")]
        except Exception:
            pass

    return ["Living Area"]


def room_bboxes(
    canonical: dict[str, Any],
    all_sections: bool = False,
) -> dict[str, list[float]]:
    """Map each room label to its bounding box [x, y, w, h] in world/plan coordinates.

    Uses reconstructed architectural boundaries when available, falling back to furniture bounds.
    """
    furniture = canonical.get("furniture", []) or []
    walls = canonical.get("structured_walls") or canonical.get("walls") or []
    doors = canonical.get("doors")
    windows = canonical.get("windows")

    result: dict[str, list[float]] = {}
    if walls and furniture:
        try:
            from app.services import architectural_service
            reconstructed = architectural_service.reconstruct_rooms(
                furniture=furniture,
                structured_walls=walls,
                doors=doors,
                windows=windows,
            )
            for r in reconstructed:
                lbl = r.get("label")
                bbox = r.get("bbox")
                if lbl and bbox:
                    norm = _normalize_section_name(lbl)
                    result[norm] = bbox
                    result[lbl] = bbox
        except Exception:
            pass

    for label, items in group_by_room(furniture):
        if not items:
            continue
        norm = _normalize_section_name(label)
        if norm not in result:
            x0 = min(float(i["cx"]) - float(i["w"]) / 2 for i in items)
            x1 = max(float(i["cx"]) + float(i["w"]) / 2 for i in items)
            y0 = min(float(i["cy"]) - float(i["h"]) / 2 for i in items)
            y1 = max(float(i["cy"]) + float(i["h"]) / 2 for i in items)
            pad = 20.0
            box = [x0 - pad, y0 - pad, (x1 - x0) + 2 * pad, (y1 - y0) + 2 * pad]
            result[norm] = box
            result[label] = box

    if all_sections:
        for sec in CANONICAL_SECTIONS:
            if sec not in result:
                result[sec] = [0.0, 0.0, 1000.0, 1000.0]
    return result


def build_room_prompts(
    canonical: dict[str, Any],
    design_intent: dict[str, Any] | None,
    requested_rooms: list[str] | None = None,
    all_sections: bool = False,
    seed: int | None = None,
) -> tuple[str | None, list[tuple[str, str, int, int]]]:
    """Return (style, [(room_label, prompt, width, height)]). One entry per room (Phases 2, 3, 10)."""
    intent = design_intent or canonical.get("design_intent") or {}
    style = _style(design_intent, canonical)
    furniture = canonical.get("furniture", []) or []
    doors = canonical.get("doors")
    windows = canonical.get("windows")

    placed_groups = group_by_room(furniture) if furniture else []
    # User-defined room tags (e.g. "Master Bedroom") -> section, injected as styling
    # context only. Never alters furniture, geometry, or room assignment.
    section_tag_map = tags_by_section(canonical)
    placed_map: dict[str, list[dict[str, Any]]] = {}
    for lbl, items in placed_groups:
        norm = _normalize_section_name(lbl)
        placed_map[norm] = items
        placed_map[lbl] = items

    bboxes = room_bboxes(canonical, all_sections=all_sections)

    # Per-room doors/windows/dimensions/geometry_source from the authoritative
    # reconstruction, so each room's prompt only ever references its OWN
    # openings — never another room's door/window (previously every room's
    # camera/spatial text was built from the plan's entire global doors/
    # windows list, regardless of which room it actually belonged to).
    room_openings: dict[str, tuple[list[dict[str, Any]], list[dict[str, Any]]]] = {}
    room_dims_meta: dict[str, tuple[dict[str, Any] | None, str]] = {}
    # uid -> {nearest_wall_id, distance_to_wall_mm, wall_relationship} against
    # the plan's real extracted walls, so spatial lines can state an actual
    # measured distance instead of only a bbox-relative phrase.
    wall_info_by_uid: dict[str, dict[str, Any]] = {}
    walls = canonical.get("structured_walls") or canonical.get("walls") or []
    if walls and furniture:
        try:
            from app.services import architectural_service

            reconstructed = architectural_service.reconstruct_rooms(
                furniture=furniture, structured_walls=walls, doors=doors, windows=windows,
            )
            for r in reconstructed:
                lbl = r.get("label")
                if not lbl:
                    continue
                entry = (r.get("doors") or [], r.get("windows") or [])
                meta = (r.get("dimensions"), r.get("geometry_source") or "furniture_fallback")
                for key in (lbl, _normalize_section_name(lbl)):
                    room_openings[key] = entry
                    room_dims_meta[key] = meta

            for enriched in architectural_service.enrich_furniture_relationships(furniture, walls):
                uid = enriched.get("uid")
                if uid:
                    wall_info_by_uid[str(uid)] = {
                        "nearest_wall_id": enriched.get("nearest_wall_id"),
                        "distance_to_wall_mm": enriched.get("distance_to_wall_mm"),
                        "wall_relationship": enriched.get("wall_relationship"),
                    }
        except Exception:
            pass

    target_sections: list[str]
    if requested_rooms:
        target_sections = [_normalize_section_name(r) for r in requested_rooms]
    elif all_sections:
        target_sections = list(CANONICAL_SECTIONS)
    elif placed_groups:
        target_sections = get_eligible_sections(canonical)
    else:
        w, h = _room_dims([])
        return style, [("Interior", _room_prompt("residential interior", [], intent, seed=seed), w, h)]

    rooms_res: list[tuple[str, str, int, int]] = []
    seen: set[str] = set()
    for idx, section in enumerate(target_sections):
        if section in seen:
            continue
        seen.add(section)
        items = placed_map.get(section)
        if items is None:
            for k, v in placed_map.items():
                if k.lower() == section.lower():
                    items = v
                    break
        if not items:
            # No real furniture placed for this section — never fabricate a
            # layout to render. Skip it entirely (the caller sees fewer than
            # the requested room count and reports it as geometry-unavailable,
            # instead of sending the provider an invented inventory).
            continue

        width, height = _room_dims(items)
        room_box = bboxes.get(section)
        if room_box is None and items:
            xs = [float(i["cx"]) for i in items]
            ys = [float(i["cy"]) for i in items]
            room_box = [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]
        bbox_tuple = (
            room_box[0],
            room_box[1],
            room_box[0] + room_box[2],
            room_box[1] + room_box[3],
        ) if room_box else (0.0, 0.0, 1000.0, 1000.0)

        # Never fall back to the plan's global doors/windows here — a room
        # with no reconstructed opening data gets none in its prompt rather
        # than (possibly wrongly) inheriting every other room's openings.
        room_doors, room_windows = room_openings.get(section, ([], []))
        dims_meta, geom_source = room_dims_meta.get(section, (None, "furniture_fallback"))

        # Bedroom number drives the cycling material palette; other rooms use 1.
        room_index = 1
        if "bedroom" in section.lower():
            num_match = re.search(r"(\d+)", section)
            if num_match:
                room_index = int(num_match.group(1))

        room_seed = (seed + idx * 104729) % (2**31) if seed is not None else None
        prompt_text = _room_prompt(
            section,
            items,
            intent,
            bbox=bbox_tuple,
            doors=room_doors,
            windows=room_windows,
            seed=room_seed,
            dims_meta=dims_meta,
            geom_source=geom_source,
            wall_info=wall_info_by_uid,
            room_index=room_index,
        )
        # Append the user's room designation as styling context ONLY — the AI may use
        # it to theme materials/lighting/decor, never to change the layout, counts,
        # positions, walls, doors, or windows (which the prompt already locks).
        tag_name = section_tag_map.get(section) or section_tag_map.get(
            _normalize_section_name(section)
        )
        if tag_name:
            prompt_text = (
                f"{prompt_text}\n\nUser room designation: \"{tag_name}\". Treat this only as "
                "interior-design intent for materials, lighting, textures and decor styling; "
                "do NOT add, remove, move, resize or re-type any furniture, walls, doors or "
                "windows — the layout above remains exact."
            )
        rooms_res.append((section, prompt_text, width, height))

    return style, rooms_res

