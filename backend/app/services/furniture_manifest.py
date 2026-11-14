"""Authoritative furniture manifest (spec §2) built from the canonical scene.

The manifest is the ground-truth per-room inventory the AI render must preserve
exactly — it never invents, drops, moves, rotates, resizes, or substitutes an
item. It is built with the SAME anchor-seeded room grouping the prompt uses
(``prompt_service.group_by_room``), so the manifest and the prompt always agree
on which items belong to which room.

Used to:
- hard-gate generation (never render a room that has no authoritative furniture),
- record the exact expected inventory alongside each render (debug + response),
- give the post-generation fidelity check something concrete to compare against,
- be the SINGLE SOURCE for the prompt's authoritative inventory line
  (``compact_inventory_line``) and a readable preservation instruction block
  (``to_markdown``) — the Markdown/text and the JSON share this one builder.

This module is provider-agnostic: it works whether the render is text-to-image
or image-to-image, and it never mutates the canonical scene. All binding fields
(``design_version_id``, ``geometry_fingerprint``, …) are OPTIONAL and additive —
a caller that does not supply them gets ``None`` and the legacy shape plus the
new keys, so existing readers are unaffected.
"""

import hashlib
import json
from typing import Any

from app.data import furniture_catalog
from app.services import prompt_service

# Manifest artifact schema identifier. Bump when the manifest's shape changes in a
# way a consumer must notice. The prior (unversioned) shape is treated as "1.0".
SCHEMA_VERSION = "mynest.furniture_manifest/1.1"

# The canonical furniture transforms are 2D floor-plan coordinates. We do NOT assert a
# physical scale (mm/cm) here — the canonical data does not carry a unit, and inventing
# one would violate "report the limitation rather than invent values" (spec §5). The
# coordinate system IS known from the renderer/prompt code (top-down, origin top-left,
# +x right, +y DOWN — see ``prompt_service._position_phrase``), so it is stated honestly.
UNITS = "plan_units"  # canonical 2D plan coordinate units; physical scale not asserted
COORDINATE_SYSTEM = "2d_top_down:origin=top_left,x=right,y=down"

# Openings placed on the canvas are architecture, not "furniture" — they are
# validated as doors/windows, so they are excluded from the furniture count.
_OPENING_IDS = {"window", "bay-window-seat", "door"}


def _name_for(item_id: str, fallback: dict[str, Any]) -> str:
    if fallback.get("_name"):
        return str(fallback["_name"])
    if fallback.get("name"):
        return str(fallback["name"])
    if item_id:
        desc = furniture_catalog.describe(item_id)
        if desc and desc[0]:
            return desc[0]
        return item_id.replace("-", " ").replace("_", " ").title()
    return "Furniture Item"


def _entry(f: dict[str, Any]) -> dict[str, Any]:
    item_id = str(f.get("item_id", ""))
    return {
        "uid": str(f.get("uid", "")) or None,
        "item_id": item_id,
        "name": _name_for(item_id, f),
        "cx": float(f.get("cx", 0.0)),
        "cy": float(f.get("cy", 0.0)),
        "w": float(f.get("w", 0.0)),
        "h": float(f.get("h", 0.0)),
        "rotation": float(f.get("rotation", 0.0)),
        "is_opening": item_id in _OPENING_IDS,
    }


def _manifest_fingerprint(
    entries: list[dict[str, Any]],
    room_label: str | None,
    design_version_id: str | None,
) -> str:
    """Deterministic, stable fingerprint of a room manifest's identity + contents.

    Same snapshot + same room + same items (uid/type/transform) => same fingerprint,
    so it is reproducible provenance (spec §11) and never image-derived. Independent of
    the (volatile) ``geometry_fingerprint`` passed in, so recomputing it for the same
    inventory is stable across runs."""
    basis = {
        "schema": SCHEMA_VERSION,
        "design_version_id": design_version_id,
        "room_label": room_label,
        "items": [
            [e["uid"], e["item_id"], e["cx"], e["cy"], e["w"], e["h"], e["rotation"], e["is_opening"]]
            for e in entries
        ],
    }
    blob = json.dumps(basis, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def build_room_manifest(
    items: list[dict[str, Any]],
    *,
    room_label: str | None = None,
    design_version_id: str | None = None,
    geometry_fingerprint: str | None = None,
) -> dict[str, Any]:
    """Manifest for one room's placed items.

    Binding keys (``schema_version``/``room_label``/``design_version_id``/
    ``geometry_fingerprint``/``units``/``coordinate_system``/``manifest_fingerprint``)
    are additive; ``furniture_count``/``counts``/``items``/``door_count``/
    ``window_count`` keep their legacy shape and meaning."""
    entries = [_entry(f) for f in items]
    furniture = [e for e in entries if not e["is_opening"]]
    counts: dict[str, int] = {}
    for e in furniture:
        counts[e["name"]] = counts.get(e["name"], 0) + 1
    return {
        "schema_version": SCHEMA_VERSION,
        "room_label": room_label,
        "design_version_id": design_version_id,
        "geometry_fingerprint": geometry_fingerprint,
        "units": UNITS,
        "coordinate_system": COORDINATE_SYSTEM,
        "manifest_fingerprint": _manifest_fingerprint(entries, room_label, design_version_id),
        "furniture_count": len(furniture),
        "counts": counts,
        "items": entries,
        "door_count": sum(1 for e in entries if e["item_id"] == "door"),
        "window_count": sum(
            1 for e in entries if e["item_id"] in ("window", "bay-window-seat")
        ),
    }


def build_manifest(
    canonical: dict[str, Any],
    merge_map: dict[str, str] | None = None,
    containment_map: dict[str, str] | None = None,
    *,
    design_version_id: str | None = None,
    geometry_fingerprint: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Map each room label -> its authoritative manifest (rooms with no placed
    furniture are omitted, matching the prompt builder which never fabricates
    a layout for an empty section). ``merge_map`` (AIR-03) keeps the manifest consistent
    with the merged grouping (a merged Dining joins the Kitchen/Living manifest).
    ``containment_map`` (Step 2P) keeps it consistent with authoritative containment so the
    inventory gate never flags a section for furniture that geometry places elsewhere.

    ``design_version_id``/``geometry_fingerprint`` bind every room manifest to the exact
    immutable snapshot it was built from (additive; ``None`` = legacy/unbound)."""
    furniture = canonical.get("furniture") or []
    result: dict[str, dict[str, Any]] = {}
    for label, items in prompt_service.group_by_room(furniture, merge_map, containment_map):
        if not items:
            continue
        m = build_room_manifest(
            items,
            room_label=label,
            design_version_id=design_version_id,
            geometry_fingerprint=geometry_fingerprint,
        )
        result[label] = m
        result[prompt_service._normalize_section_name(label)] = m
    return result


def room_manifest(
    canonical: dict[str, Any],
    room_label: str,
    merge_map: dict[str, str] | None = None,
    containment_map: dict[str, str] | None = None,
    *,
    design_version_id: str | None = None,
    geometry_fingerprint: str | None = None,
) -> dict[str, Any] | None:
    """The manifest for one room label, tolerant of exact/normalized/case forms."""
    manifest = build_manifest(
        canonical, merge_map, containment_map,
        design_version_id=design_version_id,
        geometry_fingerprint=geometry_fingerprint,
    )
    if room_label in manifest:
        return manifest[room_label]
    norm = prompt_service._normalize_section_name(room_label)
    if norm in manifest:
        return manifest[norm]
    for k, v in manifest.items():
        if k.lower().strip() == room_label.lower().strip():
            return v
    return None


# ── derived representations (one source of truth: the structured manifest) ─────

def compact_inventory_line(manifest: dict[str, Any] | None) -> str:
    """The prompt's authoritative inventory phrase, derived FROM the manifest.

    Counts EVERY placed item (furniture + any window/door placed as an item), in
    first-appearance order, as ``"2x Side Table, 1x Bed, 1x Window"``. This is the
    single source the room prompt uses for its lead inventory sentence, so the text
    the model receives and the JSON manifest can never silently diverge."""
    items = (manifest or {}).get("items") or []
    counts: dict[str, int] = {}
    order: list[str] = []
    for it in items:
        name = str(it.get("name") or "Furniture Item")
        if name not in counts:
            order.append(name)
        counts[name] = counts.get(name, 0) + 1
    return ", ".join(f"{counts[n]}x {n}" for n in order)


def expected_inventory(manifest: dict[str, Any] | None) -> dict[str, Any]:
    """Compact expected-FURNITURE summary (openings excluded) for output reconciliation
    and provenance: counts by name, stable uids, and the totals."""
    items = (manifest or {}).get("items") or []
    furniture = [e for e in items if not e.get("is_opening")]
    return {
        "furniture_count": len(furniture),
        "counts": dict((manifest or {}).get("counts") or {}),
        "furniture_uids": sorted(str(e["uid"]) for e in furniture if e.get("uid")),
        "opening_count": sum(1 for e in items if e.get("is_opening")),
    }


def binding(manifest: dict[str, Any] | None) -> dict[str, Any]:
    """The manifest's provenance binding (which design version/room/schema it describes),
    for attaching to an output assessment so the assessment is provably tied to this
    exact manifest."""
    m = manifest or {}
    return {
        "schema_version": m.get("schema_version"),
        "design_version_id": m.get("design_version_id"),
        "geometry_fingerprint": m.get("geometry_fingerprint"),
        "manifest_fingerprint": m.get("manifest_fingerprint"),
        "room_label": m.get("room_label"),
        "units": m.get("units"),
        "coordinate_system": m.get("coordinate_system"),
    }


def to_markdown(manifest: dict[str, Any] | None) -> str:
    """Readable furniture-preservation instructions generated FROM the structured
    manifest (spec §6). Lists the ACTUAL catalog items/counts in this design — never
    illustrative/example furniture — and the strict preservation rules. Shares the one
    builder above, so it can never diverge from the JSON manifest."""
    m = manifest or {}
    lbl = m.get("room_label") or "this room"
    items = m.get("items") or []
    furniture = [e for e in items if not e.get("is_opening")]
    lines: list[str] = []
    lines.append(f"# Furniture preservation manifest — {lbl}")
    ver = m.get("design_version_id")
    if ver:
        lines.append(f"_Design version `{ver}` · manifest `{m.get('manifest_fingerprint')}`_")
    lines.append("")
    if not furniture:
        lines.append("_No furniture is placed in this room._")
    else:
        lines.append(
            f"Expected furniture ({m.get('furniture_count', len(furniture))} item(s)) — "
            "render each exactly once, no more, no fewer:"
        )
        for name, n in (m.get("counts") or {}).items():
            lines.append(f"- {n}× {name}")
        win = m.get("window_count", 0)
        door = m.get("door_count", 0)
        if win or door:
            lines.append("")
            lines.append(
                f"Openings to preserve (architecture, not furniture): "
                f"{door} door(s), {win} window(s)."
            )
    lines.append("")
    lines.append("## Rules (non-negotiable)")
    lines.extend([
        "- Render EVERY listed item; do not omit any.",
        "- Do NOT add, duplicate, substitute, merge, or invent furniture or decor.",
        "- Preserve each item's identity and recognizable type.",
        "- Preserve the canonical arrangement and room assignment.",
        "- Do NOT alter walls, doors, windows, room boundaries, or proportions.",
        "- Improve only materials, textures, lighting, and finishes — within this layout.",
        "- Do NOT invent furniture or decor to fill empty space.",
        "- If an item cannot be represented reliably, do NOT claim verified preservation.",
    ])
    return "\n".join(lines)
