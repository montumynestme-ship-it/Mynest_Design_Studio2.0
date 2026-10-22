"""Deterministic, detector-free inventory-mismatch assessment (Phase 4C Step 2K).

Compares a room's EXPECTED furniture manifest (the authoritative canonical
inventory, openings excluded) against the furniture inventory of the SCENE ROOM
that the render's SELECTED deterministic base actually encodes.

A deterministic base render is a WebGL capture of exactly one scene room's
furniture, so that room's furniture uid set is a faithful, offline proxy for what
the base image shows — and therefore for what the AI model was given to preserve.
This module answers one narrow, demonstrable question per render:

    "Does the deterministic base that was actually selected for this section
     contain the furniture uids the section's prompt expects it to preserve?"

Scope / guarantees:
  * PURE + OFFLINE — no YOLO / OWLv2 / AI-output detections / uncalibrated scores.
  * Compares STABLE furniture uids, never names alone.
  * NEVER changes grouping, geometry, placement, prompts, or any render decision.
  * INFORMATIONAL ONLY — it does not verify the AI OUTPUT image; it reports a
    limitation of the deterministic base the model was shown.
"""

from __future__ import annotations

from typing import Any

from app.services.furniture_manifest import _OPENING_IDS

# Openings are validated as doors/windows elsewhere and are excluded from a FURNITURE
# inventory comparison. The authoritative opening-type set is owned by
# ``furniture_manifest`` (the same set its ``is_opening`` flag is derived from); it is
# reused here verbatim so the two can never drift out of sync (Step 2L, Correction 2).

MATCH = "MATCH"
MISMATCH = "MISMATCH"
NOT_ASSESSABLE = "NOT_ASSESSABLE"


def _furniture_uid_index(items: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    """Stable-uid -> item for FURNITURE only (openings excluded, uid-less skipped)."""
    out: dict[str, dict[str, Any]] = {}
    for it in items or []:
        if str(it.get("item_id", "")) in _OPENING_IDS:
            continue
        uid = it.get("uid")
        if uid:
            out[str(uid)] = it
    return out


def assess_section_base_inventory(
    manifest: dict[str, Any] | None,
    base_room: dict[str, Any] | None,
    scene_rooms: list[dict[str, Any]] | None,
) -> tuple[str | None, dict[str, Any] | None]:
    """Return ``(status, reason)`` for one render.

    Args:
        manifest: the section's authoritative manifest (``furniture_manifest``);
            its ``items`` carry stable ``uid`` + ``item_id`` + ``is_opening``.
            ``None`` for an empty/unknown section.
        base_room: the resolved scene room whose deterministic base PNG was
            SELECTED for this render (caller resolves it via the SAME key the base
            lookup used — this module never guesses which room was selected).
            ``None`` when no base was used or the key did not resolve.
        scene_rooms: all scene rooms, used only to LOCATE a missing expected item
            elsewhere in the scene (which makes an absence demonstrable rather
            than merely unexplained). ``None``/empty is tolerated.

    Status semantics:
        MISMATCH         — at least one expected furniture uid is absent from the
                           selected base's furniture uid set AND that uid is
                           present elsewhere in the scene (so it was demonstrably
                           routed away from this base, not merely unplaced).
        MATCH            — every expected furniture uid is present in the selected
                           base's furniture uid set.
        NOT_ASSESSABLE   — no expected inventory, an expected furniture item lacks a
                           stable uid (so it cannot be checked), no resolved base
                           room, or an expected item is absent but not locatable
                           anywhere in the scene (uncertain — never asserted as a
                           definitive match or mismatch).
    """
    # Expected FURNITURE items (openings excluded). An expected furniture item without
    # a stable uid cannot be checked against the base; returning MATCH over only the
    # uid-bearing subset would silently ignore it, so the whole section is
    # NOT_ASSESSABLE in that case (Step 2L, Correction 1).
    furniture_items = [
        it for it in ((manifest or {}).get("items") or [])
        if str(it.get("item_id", "")) not in _OPENING_IDS
    ]
    if not furniture_items:
        return NOT_ASSESSABLE, {"reason": "no expected furniture inventory with stable uids"}
    if any(not it.get("uid") for it in furniture_items):
        return NOT_ASSESSABLE, {
            "reason": "an expected furniture item lacks a stable uid; inventory "
                      "cannot be verified without silently ignoring it",
        }
    expected = {str(it["uid"]): it for it in furniture_items}

    if base_room is None:
        return NOT_ASSESSABLE, {
            "reason": "no deterministic base scene room resolved for this render",
            "expected_count": len(expected),
        }

    base_uids = set(_furniture_uid_index(base_room.get("furniture")))
    reason: dict[str, Any] = {
        "base_room_id": base_room.get("id"),
        "base_room_label": base_room.get("label"),
        "base_room_status": str(base_room.get("validation_status", "")).upper() or None,
        "expected_count": len(expected),
    }

    missing = [uid for uid in expected if uid not in base_uids]
    if not missing:
        return MATCH, reason

    # An expected item absent from THIS base is a DEMONSTRABLE mismatch only when it
    # exists elsewhere in the scene — i.e. it was placed, but routed to a different
    # room than the base the section rendered against. An item we cannot locate
    # anywhere is left uncertain (never a false definitive), honouring the rule that
    # a missing uid from an uncertain fallback room is not a mismatch until the
    # comparison is shown to be meaningful.
    scene_uids: set[str] = set()
    for r in scene_rooms or []:
        scene_uids |= set(_furniture_uid_index(r.get("furniture")))
    demonstrable = [uid for uid in missing if uid in scene_uids]
    if not demonstrable:
        return NOT_ASSESSABLE, {
            **reason,
            "reason": "expected item(s) absent from the selected base and not "
                      "locatable elsewhere in the scene",
            "missing_count": len(missing),
        }

    return MISMATCH, {
        **reason,
        "reason": "the selected deterministic base omits furniture the section's "
                  "prompt expects; the item(s) exist elsewhere in the scene",
        "missing_uids": demonstrable,
        "missing_types": sorted(
            {str(expected[uid].get("name") or expected[uid].get("item_id") or uid)
             for uid in demonstrable}
        ),
        "missing_count": len(demonstrable),
    }
