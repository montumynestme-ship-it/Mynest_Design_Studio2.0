"""Authoritative furniture manifest (spec §2) built from the canonical scene.

The manifest is the ground-truth per-room inventory the AI render must preserve
exactly — it never invents, drops, moves, rotates, resizes, or substitutes an
item. It is built with the SAME anchor-seeded room grouping the prompt uses
(``prompt_service.group_by_room``), so the manifest and the prompt always agree
on which items belong to which room.

Used to:
- hard-gate generation (never render a room that has no authoritative furniture),
- record the exact expected inventory alongside each render (debug + response),
- give the post-generation fidelity check something concrete to compare against.

This module is provider-agnostic: it works whether the render is text-to-image
or image-to-image, and it never mutates the canonical scene.
"""

from typing import Any

from app.data import furniture_catalog
from app.services import prompt_service

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


def build_room_manifest(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Manifest for one room's placed items."""
    entries = [_entry(f) for f in items]
    furniture = [e for e in entries if not e["is_opening"]]
    counts: dict[str, int] = {}
    for e in furniture:
        counts[e["name"]] = counts.get(e["name"], 0) + 1
    return {
        "furniture_count": len(furniture),
        "counts": counts,
        "items": entries,
        "door_count": sum(1 for e in entries if e["item_id"] == "door"),
        "window_count": sum(
            1 for e in entries if e["item_id"] in ("window", "bay-window-seat")
        ),
    }


def build_manifest(canonical: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map each room label -> its authoritative manifest (rooms with no placed
    furniture are omitted, matching the prompt builder which never fabricates
    a layout for an empty section)."""
    furniture = canonical.get("furniture") or []
    result: dict[str, dict[str, Any]] = {}
    for label, items in prompt_service.group_by_room(furniture):
        if not items:
            continue
        m = build_room_manifest(items)
        result[label] = m
        result[prompt_service._normalize_section_name(label)] = m
    return result


def room_manifest(canonical: dict[str, Any], room_label: str) -> dict[str, Any] | None:
    """The manifest for one room label, tolerant of exact/normalized/case forms."""
    manifest = build_manifest(canonical)
    if room_label in manifest:
        return manifest[room_label]
    norm = prompt_service._normalize_section_name(room_label)
    if norm in manifest:
        return manifest[norm]
    for k, v in manifest.items():
        if k.lower().strip() == room_label.lower().strip():
            return v
    return None
