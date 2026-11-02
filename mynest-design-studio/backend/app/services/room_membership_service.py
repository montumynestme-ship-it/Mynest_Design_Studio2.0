"""Authoritative, deterministic dynamic room-grouping resolution (AIR-03).

The canonical 2D design is the single source of truth. A designer may *optionally*
assign an open-plan item (today: a dining table) an authoritative room membership —
``KITCHEN``, ``LIVING_AREA`` or ``INDEPENDENT_DINING`` — carried on the canonical
furniture item's ``room_membership`` field (schemas/floor_plan.LayoutItem).

This module resolves that intent against the *existing* deterministic
room-reconstruction evidence (CONFIRMED wall-topology rooms from
``architectural_service.reconstruct_rooms``) and returns, per dining item, either a
RESOLVED authoritative group id or a REVIEW_REQUIRED outcome with a structured
reason. It is the single policy both the prompt-section side and the scene/base side
must consume so they can never invent contradictory partitions.

Hard guarantees (SPEC §3 / §5 / §11):
  * PURE + OFFLINE — reads canonical furniture + reconstructed scene rooms only.
  * NEVER moves, duplicates, retypes, re-counts or re-places furniture; never alters
    walls/openings/boundaries; never changes room reconstruction or thresholds.
  * Geometry evidence = shared CONFIRMED reconstructed room (connected open-plan
    region). It NEVER uses visual proximity, a distance threshold, or furniture
    nearness as proof of membership, and never forces a merge to satisfy a check.
  * The styling-only ``room-tag`` annotation is NOT read here; only the structured
    ``room_membership`` field is authoritative.
  * Insufficient / conflicting / missing evidence → REVIEW_REQUIRED (block auto
    render), never a silent default.
"""

from __future__ import annotations

from typing import Any

from app.services import prompt_service

# Allowed authoritative membership values (SPEC §4). Kept here as the single source
# of truth; the schema field accepts any str and is validated by this module so an
# unknown value degrades safely to REVIEW_REQUIRED rather than raising.
KITCHEN = "KITCHEN"
LIVING_AREA = "LIVING_AREA"
INDEPENDENT_DINING = "INDEPENDENT_DINING"
VALID_MEMBERSHIPS: frozenset[str] = frozenset({KITCHEN, LIVING_AREA, INDEPENDENT_DINING})

# Outcome statuses.
RESOLVED = "RESOLVED"
REVIEW_REQUIRED = "REVIEW_REQUIRED"

# The destination anchor types for each membership, reused verbatim from the existing
# grouping catalog so they can never drift (dynamic across plans — no hardcoded uid /
# room name / coordinate). A "dining item" is any catalog dining seed.
_DINING_IDS = prompt_service._DINING_SEEDS
_ANCHOR_IDS: dict[str, frozenset[str]] = {
    KITCHEN: frozenset(prompt_service._KITCHEN_IDS),
    LIVING_AREA: frozenset(prompt_service._SOFAS),
}


def _uid(item: dict[str, Any]) -> str | None:
    u = item.get("uid") or item.get("id")
    return str(u) if u else None


def _confirmed_room_of(uid: str, scene_rooms: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The single CONFIRMED reconstructed room whose furniture contains ``uid``,
    or ``None`` if the item is not placed inside any CONFIRMED room (e.g. it only
    falls in an UNCERTAIN fallback twin, or no room at all). Membership can only be
    *validated* against CONFIRMED wall-topology evidence."""
    for r in scene_rooms or []:
        if str(r.get("validation_status", "")).upper() != "CONFIRMED":
            continue
        for f in r.get("furniture", []) or []:
            if _uid(f) == uid:
                return r
    return None


def _room_has_anchor(room: dict[str, Any] | None, anchor_ids: frozenset[str]) -> bool:
    if not room:
        return False
    return any(
        str(f.get("item_id", "")) in anchor_ids
        for f in room.get("furniture", []) or []
    )


def _shares_confirmed_room_with_anchor(
    dining_room: dict[str, Any] | None, anchor_ids: frozenset[str]
) -> bool:
    """True iff the dining item's CONFIRMED room also contains a destination anchor —
    i.e. they are the SAME connected open-plan region (no separating wall), by
    reconstruction evidence alone."""
    return _room_has_anchor(dining_room, anchor_ids)


def _any_confirmed_room_with_anchor(
    scene_rooms: list[dict[str, Any]], anchor_ids: frozenset[str]
) -> dict[str, Any] | None:
    for r in scene_rooms or []:
        if str(r.get("validation_status", "")).upper() != "CONFIRMED":
            continue
        if _room_has_anchor(r, anchor_ids):
            return r
    return None


def _decide_for_dining(
    item: dict[str, Any], scene_rooms: list[dict[str, Any]]
) -> dict[str, Any]:
    """Resolve one dining item. Returns a structured decision dict:
    ``{uid, membership, status, group_room_id, reason}``."""
    uid = _uid(item)
    membership = item.get("room_membership")
    base = {"uid": uid, "membership": membership}

    if uid is None:
        return {**base, "status": REVIEW_REQUIRED, "group_room_id": None,
                "reason": "INSUFFICIENT_EVIDENCE: dining item has no stable uid"}

    dining_room = _confirmed_room_of(uid, scene_rooms)
    any_kitchen = any(str(f.get("item_id", "")) in _ANCHOR_IDS[KITCHEN]
                      for r in (scene_rooms or [])
                      if str(r.get("validation_status", "")).upper() == "CONFIRMED"
                      for f in (r.get("furniture", []) or []))

    # ── Case D — no authoritative membership (untagged / legacy) ───────────────
    if membership is None:
        if dining_room is None:
            # Not inside any CONFIRMED room (UNCERTAIN twin or unplaced): cannot be
            # validated either way — honest review, never a silent default.
            return {**base, "status": REVIEW_REQUIRED, "group_room_id": None,
                    "reason": "INSUFFICIENT_EVIDENCE: dining not inside a CONFIRMED room"}
        shares_kitchen = _shares_confirmed_room_with_anchor(dining_room, _ANCHOR_IDS[KITCHEN])
        shares_living = _shares_confirmed_room_with_anchor(dining_room, _ANCHOR_IDS[LIVING_AREA])
        if shares_kitchen or shares_living:
            # Genuine open-plan (dining shares a CONFIRMED region with a
            # kitchen/living anchor) but the designer gave no assignment → block.
            return {**base, "status": REVIEW_REQUIRED, "group_room_id": dining_room.get("id"),
                    "reason": "MISSING_MEMBERSHIP: open-plan dining shares a CONFIRMED "
                              "room with a kitchen/living anchor but has no explicit "
                              "membership; automatic rendering blocked (SPEC §5 Case D)"}
        # Dining is in its own CONFIRMED room with no kitchen/living anchor →
        # genuinely independent; keep its separate render (Case C).
        return {**base, "status": RESOLVED, "group_room_id": dining_room.get("id"),
                "reason": "INDEPENDENT_BY_GEOMETRY: dining occupies its own CONFIRMED "
                          "room with no kitchen/living anchor"}

    # ── Invalid value → review (never guess) ──────────────────────────────────
    if membership not in VALID_MEMBERSHIPS:
        return {**base, "status": REVIEW_REQUIRED, "group_room_id": None,
                "reason": f"INVALID_MEMBERSHIP: {membership!r} is not one of "
                          f"{sorted(VALID_MEMBERSHIPS)}"}

    # ── Case C (explicit) — INDEPENDENT_DINING ────────────────────────────────
    if membership == INDEPENDENT_DINING:
        if dining_room is None:
            return {**base, "status": REVIEW_REQUIRED, "group_room_id": None,
                    "reason": "INSUFFICIENT_EVIDENCE: dining not inside a CONFIRMED room"}
        if _shares_confirmed_room_with_anchor(dining_room, _ANCHOR_IDS[KITCHEN]) or \
           _shares_confirmed_room_with_anchor(dining_room, _ANCHOR_IDS[LIVING_AREA]):
            return {**base, "status": REVIEW_REQUIRED, "group_room_id": dining_room.get("id"),
                    "reason": "CONFLICT: tagged INDEPENDENT_DINING but geometry shows the "
                              "dining shares a CONFIRMED open-plan room with a "
                              "kitchen/living anchor"}
        return {**base, "status": RESOLVED, "group_room_id": dining_room.get("id"),
                "reason": "INDEPENDENT: explicit tag matches independent CONFIRMED room"}

    # ── Cases A/B — KITCHEN or LIVING_AREA ────────────────────────────────────
    anchor_ids = _ANCHOR_IDS[membership]
    if dining_room is None:
        return {**base, "status": REVIEW_REQUIRED, "group_room_id": None,
                "reason": "INSUFFICIENT_EVIDENCE: dining not inside a CONFIRMED room, "
                          "so the assignment cannot be validated against wall topology"}

    if _shares_confirmed_room_with_anchor(dining_room, anchor_ids):
        # The dining table and a destination anchor occupy the SAME CONFIRMED
        # (connected, no separating wall) region → the assignment is supported.
        return {**base, "status": RESOLVED, "group_room_id": dining_room.get("id"),
                "reason": f"SUPPORTED: dining shares its CONFIRMED room with a "
                          f"{membership} anchor (connected open-plan region)"}

    # The dining is CONFIRMED-placed but the destination anchor is NOT in that room.
    other = _any_confirmed_room_with_anchor(scene_rooms, anchor_ids)
    if other is not None:
        # Anchor exists in a DIFFERENT CONFIRMED room → a confirmed wall separates
        # them → the tag crosses a separating wall → conflict (never force a merge).
        return {**base, "status": REVIEW_REQUIRED, "group_room_id": dining_room.get("id"),
                "reason": f"CONFLICT: {membership} anchor is in a different CONFIRMED "
                          f"room (a separating wall divides them); will not force a merge"}

    # No destination anchor is confirmed anywhere → cannot validate the assignment.
    return {**base, "status": REVIEW_REQUIRED, "group_room_id": dining_room.get("id"),
            "reason": f"INSUFFICIENT_EVIDENCE: no CONFIRMED {membership} anchor to "
                      f"validate the dining assignment against"}


def resolve_dining_memberships(
    furniture: list[dict[str, Any]] | None,
    scene_rooms: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Resolve every dining item's authoritative membership (one decision per dining
    item, so each is accounted for exactly once). Non-dining furniture is untouched
    and never duplicated. Deterministic and side-effect-free.

    Each decision: ``{uid, membership, status, group_room_id, reason}`` where
    ``status`` ∈ {``RESOLVED``, ``REVIEW_REQUIRED``}.
    """
    dining = [
        f for f in (furniture or [])
        if str(f.get("item_id", "")) in _DINING_IDS
    ]
    return [_decide_for_dining(item, scene_rooms or []) for item in dining]


def has_blocking_review(decisions: list[dict[str, Any]]) -> bool:
    """True iff any dining decision requires human review (automatic rendering of the
    affected grouping must be blocked)."""
    return any(d.get("status") == REVIEW_REQUIRED for d in decisions or [])


REVIEW_REQUIRED_CODE = "MEMBERSHIP_REVIEW_REQUIRED"
MERGE_PENDING_CODE = "MEMBERSHIP_MERGE_PENDING"


def _blocking_for_decision(
    d: dict[str, Any], merge_supported: bool
) -> dict[str, Any] | None:
    """The block record for one dining decision, or ``None`` if it may render as-is.

    Two blocking cases (both must refuse BEFORE a provider call):
      * REVIEW_REQUIRED — membership is missing / conflicting / geometry-unverified.
      * MERGE_PENDING — membership is validly RESOLVED to KITCHEN/LIVING_AREA, so the
        dining belongs to that group and must NOT be rendered as its own room; until
        authoritative render-set merging exists (``merge_supported``), there is no safe
        way to render it, so it is blocked rather than silently rendered independently.
    A RESOLVED *independent* dining (INDEPENDENT_DINING or untagged-in-its-own-room)
    renders normally and is never blocked here.
    """
    uid = d.get("uid")
    if not uid:
        return None
    if d.get("status") == REVIEW_REQUIRED:
        return {"code": REVIEW_REQUIRED_CODE, "reason": d["reason"], "uid": uid}
    if (
        d.get("status") == RESOLVED
        and d.get("membership") in (KITCHEN, LIVING_AREA)
        and not merge_supported
    ):
        return {
            "code": MERGE_PENDING_CODE,
            "reason": (
                f"dining is validly assigned to {d['membership']} but authoritative "
                "render-set merging is not yet available; rendering it as a separate "
                "room would misrepresent the design, so it is blocked until the merge "
                "is implemented"
            ),
            "uid": uid,
        }
    return None


def resolve_authoritative_groups(
    furniture: list[dict[str, Any]] | None,
    scene_rooms: list[dict[str, Any]] | None,
    *,
    merge_supported: bool,
) -> dict[str, Any]:
    """The single authoritative grouping result consumed by every grouping consumer.

    Returns ``{merge_map, decisions}`` where:
      * ``merge_map``: ``{dining_uid -> "KITCHEN" | "LIVING_AREA"}`` for each dining item
        whose membership is validly RESOLVED to Kitchen/Living — i.e. the item must be
        folded into that destination render set. Empty unless ``merge_supported`` (so the
        gate's merge-pending block and this map are never both active for the same item).
      * ``decisions``: the full per-dining decision list (for surfacing/blocking).

    Deterministic and pure: it reads the structured ``room_membership`` field + the
    reconstructed CONFIRMED-room evidence only; it never moves furniture, infers from
    proximity, or guesses a destination.
    """
    decisions = resolve_dining_memberships(furniture, scene_rooms)
    merge_map: dict[str, str] = {}
    if merge_supported:
        for d in decisions:
            if (
                d.get("status") == RESOLVED
                and d.get("membership") in (KITCHEN, LIVING_AREA)
                and d.get("uid")
            ):
                merge_map[str(d["uid"])] = str(d["membership"])
    return {"merge_map": merge_map, "decisions": decisions}


# ─────────────────────────────────────────────────────────────────────────────
# AIR-03 Step 2M.1 — EXPLICIT RENDER INCLUSION (distinct from dining membership)
#
# A separate, authoritative concept: a designer may explicitly include a NON-DINING
# canonical item in a specific CONFIRMED room's deterministic render even when the
# item's footprint is OUTSIDE that room's proven floor polygon (e.g. a wall counter in
# an un-reconstructed alcove). This is the only path that places an item in a room it
# is geometrically outside of; it is EXPLICIT and AUDITABLE (driven by the user-authored
# ``render_room`` field, never by a proximity/threshold guess), and it NEVER moves,
# resizes, rotates, re-counts, or duplicates furniture — it only decides which room's
# render set references the single canonical item. Unlike the dining membership above,
# it does not merely VALIDATE geometry; it authoritatively INCLUDES. It fails safe:
# a target that is missing, unconfirmed, or ambiguous → REVIEW_REQUIRED, no move.
#
# Target space (today): the same anchor tokens as the dining destinations, reused so
# they can never drift — KITCHEN / LIVING_AREA — each resolving to the UNIQUE CONFIRMED
# room that contains an anchor of that type. A token with zero or multiple confirmed
# anchor rooms is ambiguous → REVIEW_REQUIRED.
VALID_RENDER_ROOMS: frozenset[str] = frozenset(_ANCHOR_IDS)  # {KITCHEN, LIVING_AREA}


def _confirmed_rooms_with_anchor(
    scene_rooms: list[dict[str, Any]], anchor_ids: frozenset[str]
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in scene_rooms or []:
        if str(r.get("validation_status", r.get("status", ""))).upper() != "CONFIRMED":
            continue
        if _room_has_anchor(r, anchor_ids):
            out.append(r)
    return out


def _room_of_uid(uid: str, scene_rooms: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The scene room (any status) whose furniture currently contains ``uid``."""
    for r in scene_rooms or []:
        for f in (r.get("items") or r.get("furniture") or []):
            if _uid(f) == uid:
                return r
    return None


def _decide_render_inclusion(
    item: dict[str, Any], scene_rooms: list[dict[str, Any]]
) -> dict[str, Any]:
    uid = _uid(item)
    token = item.get("render_room")
    base = {"uid": uid, "render_room": token}
    if uid is None:
        return {**base, "status": REVIEW_REQUIRED, "target_room_id": None,
                "reason": "INSUFFICIENT_EVIDENCE: item has no stable uid"}
    if token not in VALID_RENDER_ROOMS:
        return {**base, "status": REVIEW_REQUIRED, "target_room_id": None,
                "reason": f"INVALID_RENDER_ROOM: {token!r} not one of {sorted(VALID_RENDER_ROOMS)}"}

    anchor_ids = _ANCHOR_IDS[token]

    # CONTAINMENT WINS FIRST: an item firmly placed by geometry in a CONFIRMED room is
    # never overridden by an explicit tag — the tag only rescues items geometry left
    # unplaced. (Checked before target resolution so an item that is itself an anchor of
    # the token type cannot masquerade as a second candidate room.)
    confirmed_of_item = _confirmed_room_of(uid, scene_rooms)
    if confirmed_of_item is not None:
        if _room_has_anchor(confirmed_of_item, anchor_ids):
            return {**base, "status": RESOLVED, "target_room_id": confirmed_of_item.get("id"),
                    "move": False,
                    "reason": f"ALREADY_IN_TARGET: contained in a CONFIRMED {token} room; no move"}
        return {**base, "status": REVIEW_REQUIRED, "target_room_id": None, "move": False,
                "reason": f"CONFLICT: item is contained in a different CONFIRMED room than {token}; "
                          "explicit inclusion will not override confirmed geometric containment"}

    # Not in any CONFIRMED room (the out-of-polygon case): resolve the UNIQUE confirmed
    # room carrying the token's anchor and authoritatively include it there.
    targets = _confirmed_rooms_with_anchor(scene_rooms, anchor_ids)
    if len(targets) == 0:
        return {**base, "status": REVIEW_REQUIRED, "target_room_id": None, "move": False,
                "reason": f"INSUFFICIENT_EVIDENCE: no CONFIRMED {token} room (no anchor) to include into"}
    if len(targets) > 1:
        return {**base, "status": REVIEW_REQUIRED, "target_room_id": None, "move": False,
                "reason": f"AMBIGUOUS_DESTINATION: {len(targets)} CONFIRMED {token} rooms; "
                          "cannot choose from a category token alone"}
    target_id = targets[0].get("id")
    return {**base, "status": RESOLVED, "target_room_id": target_id, "move": True,
            "reason": f"INCLUDED: explicitly included in the unique CONFIRMED {token} room "
                      "(footprint may be outside its floor polygon — render-inclusion only)"}


def resolve_render_inclusions(
    furniture: list[dict[str, Any]] | None,
    scene_rooms: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Resolve explicit render-inclusion directives (``render_room``) on NON-DINING items.

    Returns ``{inclusion_map, decisions}`` where:
      * ``inclusion_map``: ``{uid -> target_confirmed_room_id}`` for each item that must be
        MOVED into a CONFIRMED room's render set (RESOLVED with ``move=True``) — i.e. it is
        not already there. Empty when nothing needs moving.
      * ``decisions``: the full per-item decision list (RESOLVED / REVIEW_REQUIRED + reason),
        for surfacing in the editor and diagnostics.

    Pure + deterministic: reads the structured ``render_room`` field and the reconstructed
    CONFIRMED-room evidence only. Dining items (``room_membership``) are untouched here.
    """
    items = [
        f for f in (furniture or [])
        if f.get("render_room") is not None
        and str(f.get("item_id", "")) not in _DINING_IDS
    ]
    decisions = [_decide_render_inclusion(it, scene_rooms or []) for it in items]
    inclusion_map: dict[str, str] = {
        str(d["uid"]): str(d["target_room_id"])
        for d in decisions
        if d.get("status") == RESOLVED and d.get("move") and d.get("uid") and d.get("target_room_id")
    }
    return {"inclusion_map": inclusion_map, "decisions": decisions}


def blocked_dining_sections(
    furniture: list[dict[str, Any]] | None,
    scene_rooms: list[dict[str, Any]] | None,
    sections: list[tuple[str, list[dict[str, Any]]]] | None,
    *,
    merge_supported: bool = False,
) -> dict[str, dict[str, Any]]:
    """Map each prompt SECTION (``group_by_room`` output ``[(label, items)]``) that must
    be refused before a provider call to a structured block record. Covers BOTH
    review-required and (while ``merge_supported`` is False) merge-pending dining — so a
    validly-tagged Kitchen/Living dining is never silently rendered as an independent
    room. The gate (G1) uses this to refuse exactly the affected section(s) while
    unrelated sections proceed (safe partial execution). Pure/read-only; never moves
    furniture, re-groups, or guesses a destination.

    Returns ``{section_label: {code, reason, uid}}``; empty when nothing is blocked.
    """
    decisions = resolve_dining_memberships(furniture, scene_rooms)
    blocking: dict[str, dict[str, Any]] = {}
    for d in decisions:
        rec = _blocking_for_decision(d, merge_supported)
        if rec is not None:
            blocking[rec["uid"]] = rec
    blocked: dict[str, dict[str, Any]] = {}
    if not blocking:
        return blocked
    for label, items in sections or []:
        for it in items or []:
            u = _uid(it)
            if u in blocking:
                blocked[str(label)] = blocking[u]
                break
    return blocked
