"""Deterministic, read-only FULL-DESIGN inventory reconciliation (Phase 4C Step 2O-A).

Workstream A ("deterministic inventory contract") asks for one explicit, auditable
answer: *is every canonical furniture item accounted for exactly once across the
render sections and the reconstructed scene, with no silent drop?* The per-section
inventory gate (``base_inventory_service``) already refuses a section whose selected
base omits expected furniture; this module adds the orthogonal, design-wide accounting
that makes a silent omission — an item that reaches NO section or NO scene room, a
duplicate uid, or an unknown furniture type — explicit rather than invisible.

Guarantees (match the existing contract's discipline):
  * PURE + OFFLINE — reads canonical furniture, reconstructed scene rooms, and the
    ``group_by_room`` sections only. No DB, no network, no paid call.
  * Uses STABLE uids as identity; never names or counts alone.
  * NEVER modifies canonical, reassigns furniture, re-groups, changes geometry, or
    gates a render. It only REPORTS; the caller decides what to surface.
  * Reuses the authoritative catalogs (``furniture_catalog``, ``_OPENING_IDS``) so the
    opening/annotation exclusions can never drift from the rest of the pipeline.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from app.data import furniture_catalog
from app.services.furniture_manifest import _OPENING_IDS


def _uid(item: dict[str, Any]) -> str | None:
    u = item.get("uid") or item.get("id")
    return str(u) if u else None


def _is_opening(item: dict[str, Any]) -> bool:
    return str(item.get("item_id", "")) in _OPENING_IDS


def _scene_room_items(room: dict[str, Any]) -> list[dict[str, Any]]:
    # A scene room exposes its furniture as either "items" (resolved rooms) or
    # "furniture" (some callers) — accept both so the reconciliation can never
    # under-count because of a key-name difference.
    return room.get("items") or room.get("furniture") or []


def reconcile_design_inventory(
    furniture: list[dict[str, Any]] | None,
    scene_rooms: list[dict[str, Any]] | None,
    sections: list[tuple[str, list[dict[str, Any]]]] | None,
) -> dict[str, Any]:
    """Account for every canonical furniture item across sections + scene rooms.

    Args:
        furniture: canonical furniture list (the design snapshot's ``furniture``).
        scene_rooms: ``scene_service.build_scene(...)["rooms"]``.
        sections: ``prompt_service.group_by_room(furniture, merge_map)`` output.

    Returns a structured diagnostic (never raises on normal input):
        {
          "ok": bool,                      # True iff no duplicate / unmapped / unaccounted
          "real_count": int,               # real furniture (openings + annotations excluded)
          "openings_excluded": [uid...],
          "annotations_excluded": [uid...],
          "uidless": [item_id...],         # real furniture with no stable uid (cannot track)
          "duplicate_uids": [uid...],
          "unmapped_types": [item_id...],  # real furniture whose type is not in the catalog
          "unaccounted_in_sections": [uid...],  # real uid in NO group_by_room section
          "unaccounted_in_scene": [uid...],     # real uid in NO scene room
        }

    A non-empty ``duplicate_uids`` / ``unmapped_types`` / ``unaccounted_*`` is the
    explicit diagnostic the pipeline previously lacked: it names the exact item(s)
    rather than letting them vanish between grouping and the scene.
    """
    furniture = furniture or []
    scene_rooms = scene_rooms or []
    sections = sections or []

    openings_excluded: list[str] = []
    annotations_excluded: list[str] = []
    uidless: list[str] = []
    real: list[dict[str, Any]] = []

    for it in furniture:
        iid = str(it.get("item_id", ""))
        uid = _uid(it)
        if furniture_catalog.is_annotation(iid):
            if uid:
                annotations_excluded.append(uid)
            continue
        if _is_opening(it):
            if uid:
                openings_excluded.append(uid)
            continue
        if uid is None:
            # A real furniture item with no stable uid cannot be tracked through the
            # pipeline — surface it explicitly instead of silently ignoring it.
            uidless.append(iid)
            continue
        real.append(it)

    real_uids = [str(it["uid"]) for it in real]
    duplicate_uids = sorted({u for u, c in Counter(real_uids).items() if c > 1})
    unmapped_types = sorted(
        {str(it.get("item_id", "")) for it in real
         if str(it.get("item_id", "")) not in furniture_catalog.FURNITURE}
    )

    in_section: set[str] = set()
    for _label, items in sections:
        for it in items or []:
            u = _uid(it)
            if u is not None and not _is_opening(it) and not furniture_catalog.is_annotation(
                str(it.get("item_id", ""))
            ):
                in_section.add(u)

    in_scene: set[str] = set()
    for r in scene_rooms:
        for it in _scene_room_items(r):
            u = _uid(it)
            if u is not None and not _is_opening(it) and not furniture_catalog.is_annotation(
                str(it.get("item_id", ""))
            ):
                in_scene.add(u)

    unaccounted_in_sections = sorted({u for u in real_uids if u not in in_section})
    unaccounted_in_scene = sorted({u for u in real_uids if u not in in_scene})

    ok = not (
        duplicate_uids
        or unmapped_types
        or unaccounted_in_sections
        or unaccounted_in_scene
        or uidless
    )

    return {
        "ok": ok,
        "real_count": len(real),
        "openings_excluded": sorted(set(openings_excluded)),
        "annotations_excluded": sorted(set(annotations_excluded)),
        "uidless": sorted(set(uidless)),
        "duplicate_uids": duplicate_uids,
        "unmapped_types": unmapped_types,
        "unaccounted_in_sections": unaccounted_in_sections,
        "unaccounted_in_scene": unaccounted_in_scene,
    }


def reconciliation_warnings(result: dict[str, Any]) -> list[str]:
    """Human-readable, explicit diagnostics for a reconciliation result (empty when ok).

    Returned as plain strings so a caller can log them non-fatally without importing
    this module's shape — the diagnostic is surfaced, never swallowed.
    """
    if result.get("ok"):
        return []
    msgs: list[str] = []
    if result.get("uidless"):
        msgs.append(f"real furniture without a stable uid (untrackable): {result['uidless']}")
    if result.get("duplicate_uids"):
        msgs.append(f"duplicate furniture uids: {result['duplicate_uids']}")
    if result.get("unmapped_types"):
        msgs.append(f"unknown furniture types (not in catalog): {result['unmapped_types']}")
    if result.get("unaccounted_in_sections"):
        msgs.append(
            "furniture uids in NO render section (would never be prompted): "
            f"{result['unaccounted_in_sections']}"
        )
    if result.get("unaccounted_in_scene"):
        msgs.append(
            "furniture uids in NO scene room (would never be rendered or inventory-checked): "
            f"{result['unaccounted_in_scene']}"
        )
    return msgs
