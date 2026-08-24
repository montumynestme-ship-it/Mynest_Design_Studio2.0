"""Server-side room-aware prompt synthesis with geometry-faithful constraint.

Groups the placed furniture into rooms and builds one geometry-faithful prompt
per room (PRD §28 Master AI Constraint injected server-side).
"""

import math
from typing import Any

from app.data import furniture_catalog

MASTER_CONSTRAINT = """\
================================================================================
CRITICAL LAYOUT & INVENTORY CONSTRAINT (NON-NEGOTIABLE):
You are rendering ONE specific room from an AUTHORITATIVE 2D floor plan.

STRUCTURAL RULES (DO NOT BREAK):
1. Wall locations, lengths/angles, room proportions and dimensions, and door/window
   positions are FIXED. Do NOT add, relocate, resize, rescale, or remove any wall,
   door, or window, and do NOT change the room's shape or proportions. Keep every
   furniture piece inside the walls — nothing may cross, overlap, or sit past a wall.
2. Render EXACTLY the furniture listed for this room, in the given relative positions
   and orientations, at realistic real-world scale. Do NOT move or reorient them.

STRICT INVENTORY (DO NOT BREAK):
3. Include ONLY the listed furniture items — nothing else. Do NOT add any extra
   furniture, plants, artwork, wall art, rugs, lamps, benches, mirrors, people, or
   decorative props that are not explicitly listed.
4. Do NOT omit any listed item. Every listed piece must appear exactly once,
   respecting the given counts, and must NOT be replaced by a different item type.
5. Depict ONLY this room. Do NOT show any other room, doorway view, or furniture
   belonging to an adjacent room.

ALLOWED (styling only): realistic materials, textures, wall/floor/ceiling finishes,
and lighting applied to the listed furniture and the room's own surfaces.

LAYOUT & INVENTORY FIDELITY > ARTISTIC CREATIVITY.
================================================================================"""


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
# so a side table placed by the sofa joins the living room, not a far bedroom.
_GENERIC_IDS = {"side-table", "floor-lamp", "desk-lamp"}
# Which seed kind each catalog room type belongs to.
_ROOM_TO_SEED_KIND = {
    "Bedroom": "bedroom",
    "Living Room": "living",
    "Dining Room": "dining",
    "Kitchen": "kitchen",
}


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
        return "Living Room"
    if "Dining Room" in rooms:
        return "Dining Room"
    if "Kitchen" in rooms:
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
    return [
        (f"{lbl} {rank[idx]}" if lbl in dup else lbl, items)
        for idx, (lbl, items) in enumerate(labeled)
    ]


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
            if str(seeds[i]["item_id"]) != str(seeds[j]["item_id"]):
                continue
            reach = 0.6 * (_seed_size(seeds[i]) + _seed_size(seeds[j]))
            if _dist(seeds[i], seeds[j]) < reach:
                parent[find(i)] = find(j)

    buckets: dict[int, list[dict[str, Any]]] = {}
    for item in enriched:
        candidates = _candidate_seeds(item, seeds)
        nearest = min(candidates, key=lambda i: _dist(item, seeds[i]))
        buckets.setdefault(find(nearest), []).append(item)

    labeled = [(_seed_label(items), items) for items in buckets.values()]
    return _number_duplicates(labeled)


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
    # Near 90° means the piece's long side runs the other way.
    if 60 <= rot <= 120:
        return "rotated 90° (long side running front-to-back)"
    return None


def _spatial_lines(items: list[dict[str, Any]]) -> list[str]:
    """Per-item 'what is where' lines so the model reproduces the real layout."""
    if not items:
        return []
    xs = [float(i["cx"]) for i in items]
    ys = [float(i["cy"]) for i in items]
    bbox = (min(xs), min(ys), max(xs), max(ys))

    lines: list[str] = []
    for it in items:
        phrase = _position_phrase(it, bbox)
        orient = _orientation(it)
        suffix = f", {orient}" if orient else ""
        lines.append(f"- {it['_name']}: {phrase}{suffix}")

    # Seating faces the TV/display when both are present.
    names = {str(i["_name"]).lower() for i in items}
    has_tv = any("tv" in n for n in names)
    has_seat = any(k in n for n in names for k in ("sofa", "couch", "chair", "recliner"))
    if has_tv and has_seat:
        lines.append("- The sofa/seating faces the TV unit across the room.")
    return lines


def _appearance_lines(items: list[dict[str, Any]]) -> list[str]:
    """One 'what each piece looks like' line per distinct item type, so the
    text-to-image model renders recognizable objects, not generic guesses."""
    seen: set[str] = set()
    lines: list[str] = []
    for it in items:
        name = str(it["_name"])
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
        name = str(i["_name"])
        if name not in counts:
            order.append(name)
        counts[name] = counts.get(name, 0) + 1
    return ", ".join(f"{counts[n]}x {n}" for n in order)


def _focal(room_label: str) -> str:
    """The wall/subject the camera should face, so the view angle suits the room."""
    label = room_label.lower()
    if "bedroom" in label:
        return "the bed and its upholstered headboard wall as the focal point"
    if "living" in label:
        return "the TV / media wall, with the sofa in the foreground"
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


def _room_prompt(
    room_label: str, items: list[dict[str, Any]], design_intent: dict[str, Any] | None
) -> str:
    intent = design_intent or {}
    parts = [
        f"This is STRICTLY a {room_label.lower()} — render only this one room and only "
        "the furniture listed below; ignore every other room.",
        f"Wide-angle architectural interior photograph of the {room_label.lower()}. "
        "Camera at standing eye level (about 1.5 m) near the room's entrance, looking "
        f"across the room toward {_focal(room_label)}. 24mm lens, natural two-point "
        "perspective, straight vertical walls (no tilt or fisheye), the whole room in "
        "frame with every listed furniture piece visible in its correct relative position.",
    ]
    if intent.get("style"):
        parts.append(f"STYLE: {intent['style']}.")
    if intent.get("mood"):
        parts.append(f"MOOD: {intent['mood']}.")
    if intent.get("colors"):
        parts.append("COLOR PALETTE: " + ", ".join(intent["colors"]) + ".")
    if intent.get("materials"):
        parts.append("MATERIALS: " + ", ".join(intent["materials"]) + ".")
    if intent.get("lighting"):
        parts.append(f"LIGHTING: {intent['lighting']}.")

    if items:
        inventory = _counted_furniture(items)
        parts.append(
            f"FURNITURE — render ONLY these, exactly, matching the counts: {inventory}. "
            "Add nothing else (no extra furniture, plants, artwork, rugs, lamps, or decor) "
            "and omit nothing."
        )
        appearance = _appearance_lines(items)
        if appearance:
            parts.append("")
            parts.append(
                "PIECE APPEARANCE (render each piece true to its real-world type; "
                "apply the chosen style/materials as its finish):"
            )
            parts.extend(appearance)
        spatial = _spatial_lines(items)
        if spatial:
            parts.append("")
            parts.append(
                "SPATIAL LAYOUT (authoritative — reproduce these relative positions "
                "and orientations exactly; the front of the room is nearest the camera):"
            )
            parts.extend(spatial)
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


def room_bboxes(canonical: dict[str, Any]) -> dict[str, list[float]]:
    """Map each room label to its furniture bounding box [x, y, w, h] in world/plan
    coordinates, so the UI can crop the 2D plan to just that room."""
    furniture = canonical.get("furniture", []) or []
    result: dict[str, list[float]] = {}
    for label, items in group_by_room(furniture):
        if not items:
            continue
        x0 = min(float(i["cx"]) - float(i["w"]) / 2 for i in items)
        x1 = max(float(i["cx"]) + float(i["w"]) / 2 for i in items)
        y0 = min(float(i["cy"]) - float(i["h"]) / 2 for i in items)
        y1 = max(float(i["cy"]) + float(i["h"]) / 2 for i in items)
        result[label] = [x0, y0, x1 - x0, y1 - y0]
    return result


def build_room_prompts(
    canonical: dict[str, Any], design_intent: dict[str, Any] | None
) -> tuple[str | None, list[tuple[str, str, int, int]]]:
    """Return (style, [(room_label, prompt, width, height)]). One entry per room."""
    intent = design_intent or canonical.get("design_intent") or {}
    style = _style(design_intent, canonical)
    furniture = canonical.get("furniture", []) or []

    if not furniture:
        w, h = _room_dims([])
        return style, [("Interior", _room_prompt("residential interior", [], intent), w, h)]

    groups = group_by_room(furniture)
    # Rooms with furniture, largest first (more meaningful renders lead).
    groups.sort(key=lambda g: len(g[1]), reverse=True)
    rooms: list[tuple[str, str, int, int]] = []
    for label, items in groups:
        width, height = _room_dims(items)
        rooms.append((label, _room_prompt(label, items, intent), width, height))
    return style, rooms
