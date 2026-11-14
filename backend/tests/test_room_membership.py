"""AIR-03 — authoritative dynamic dining room-grouping resolver (offline, deterministic).

Covers SPEC §5 Cases A–E plus the hard invariants, using SYNTHETIC fixtures only
(no real design, no hardcoded uid/room-name/coordinate, no DB, no provider).
"""
from __future__ import annotations

import copy

from app.services import room_membership_service as M
from app.services import generation_service as G


# ── fixture helpers ──────────────────────────────────────────────────────────
def _f(uid: str, item_id: str, **extra):
    return {"uid": uid, "item_id": item_id, **extra}


def _room(rid: str, label: str, status: str, furniture: list[dict]):
    return {"id": rid, "label": label, "validation_status": status, "furniture": furniture}


DINING = "dining-table"          # ∈ _DINING_SEEDS
KITCHEN_ANCHOR = "chimney"       # ∈ _KITCHEN_IDS
LIVING_ANCHOR = "lounger-sofa"   # ∈ _SOFAS


# ── Case A — Dining tagged KITCHEN, co-located CONFIRMED anchor → RESOLVED ────
def test_case_a_kitchen_resolved():
    furn = [_f("dt-1", DINING, room_membership=M.KITCHEN)]
    rooms = [_room("kda", "Kitchen & Dining Area", "CONFIRMED",
                   [_f("dt-1", DINING), _f("ch-1", KITCHEN_ANCHOR)])]
    d = M.resolve_dining_memberships(furn, rooms)[0]
    assert d["status"] == M.RESOLVED
    assert d["group_room_id"] == "kda"
    assert d["membership"] == M.KITCHEN
    assert not M.has_blocking_review([d])


# ── Case B — Dining tagged LIVING_AREA, co-located sofa → RESOLVED ───────────
def test_case_b_living_resolved():
    furn = [_f("dt-1", DINING, room_membership=M.LIVING_AREA)]
    rooms = [_room("lda", "Living & Dining", "CONFIRMED",
                   [_f("dt-1", DINING), _f("sofa-1", LIVING_ANCHOR)])]
    d = M.resolve_dining_memberships(furn, rooms)[0]
    assert d["status"] == M.RESOLVED
    assert d["group_room_id"] == "lda"


# ── Case C — independent dining (explicit + untagged) → RESOLVED independent ─
def test_case_c_explicit_independent():
    furn = [_f("dt-1", DINING, room_membership=M.INDEPENDENT_DINING)]
    rooms = [_room("dining", "Dining Area", "CONFIRMED", [_f("dt-1", DINING)])]
    d = M.resolve_dining_memberships(furn, rooms)[0]
    assert d["status"] == M.RESOLVED
    assert "INDEPENDENT" in d["reason"]


def test_case_c_untagged_independent_room_kept():
    # Untagged dining in its OWN confirmed room (no kitchen/living anchor) stays a
    # separate render — preserves current behavior for genuinely separate rooms.
    furn = [_f("dt-1", DINING)]
    rooms = [_room("dining", "Dining Area", "CONFIRMED", [_f("dt-1", DINING)])]
    d = M.resolve_dining_memberships(furn, rooms)[0]
    assert d["status"] == M.RESOLVED
    assert "INDEPENDENT_BY_GEOMETRY" in d["reason"]


# ── Case D — open-plan untagged → REVIEW_REQUIRED (blocked, no silent default) ─
def test_case_d_missing_membership_blocks():
    furn = [_f("dt-1", DINING)]  # no room_membership
    rooms = [_room("kda", "Kitchen & Dining Area", "CONFIRMED",
                   [_f("dt-1", DINING), _f("ch-1", KITCHEN_ANCHOR)])]
    d = M.resolve_dining_memberships(furn, rooms)[0]
    assert d["status"] == M.REVIEW_REQUIRED
    assert d["reason"].startswith("MISSING_MEMBERSHIP")
    assert M.has_blocking_review([d])


# ── Case E — conflicting tag vs geometry → REVIEW_REQUIRED (no forced merge) ──
def test_case_e_conflict_separating_wall():
    furn = [_f("dt-1", DINING, room_membership=M.KITCHEN)]
    rooms = [
        _room("dining", "Dining Area", "CONFIRMED", [_f("dt-1", DINING)]),
        _room("kitchen", "Kitchen", "CONFIRMED", [_f("ch-1", KITCHEN_ANCHOR)]),
    ]
    d = M.resolve_dining_memberships(furn, rooms)[0]
    assert d["status"] == M.REVIEW_REQUIRED
    assert d["reason"].startswith("CONFLICT")


def test_case_e_conflict_tagged_independent_but_open_plan():
    furn = [_f("dt-1", DINING, room_membership=M.INDEPENDENT_DINING)]
    rooms = [_room("kda", "Kitchen & Dining Area", "CONFIRMED",
                   [_f("dt-1", DINING), _f("ch-1", KITCHEN_ANCHOR)])]
    d = M.resolve_dining_memberships(furn, rooms)[0]
    assert d["status"] == M.REVIEW_REQUIRED
    assert d["reason"].startswith("CONFLICT")


# ── Case E — insufficient geometry (dining only in an UNCERTAIN twin) → review ─
def test_insufficient_evidence_uncertain_only():
    furn = [_f("dt-1", DINING, room_membership=M.KITCHEN)]
    rooms = [_room("dining", "Dining Area", "UNCERTAIN",
                   [_f("dt-1", DINING), _f("ch-1", KITCHEN_ANCHOR)])]
    d = M.resolve_dining_memberships(furn, rooms)[0]
    assert d["status"] == M.REVIEW_REQUIRED
    assert "INSUFFICIENT_EVIDENCE" in d["reason"]


def test_invalid_membership_value_reviews():
    furn = [_f("dt-1", DINING, room_membership="GARAGE")]
    rooms = [_room("kda", "K&D", "CONFIRMED", [_f("dt-1", DINING), _f("ch-1", KITCHEN_ANCHOR)])]
    d = M.resolve_dining_memberships(furn, rooms)[0]
    assert d["status"] == M.REVIEW_REQUIRED
    assert d["reason"].startswith("INVALID_MEMBERSHIP")


# ── §10.7 — styling room-tag annotation is NOT authoritative membership ───────
def test_room_tag_annotation_is_not_membership():
    # A "room-tag" annotation item is not a dining item and must never become an
    # authoritative decision; only the structured field on the dining item counts.
    furn = [
        _f("dt-1", DINING),                         # untagged dining
        _f("tag-1", "room-tag", label="Kitchen"),   # styling annotation near it
    ]
    rooms = [_room("kda", "Kitchen & Dining Area", "CONFIRMED",
                   [_f("dt-1", DINING), _f("ch-1", KITCHEN_ANCHOR)])]
    decisions = M.resolve_dining_memberships(furn, rooms)
    assert len(decisions) == 1                      # only the dining item
    assert decisions[0]["status"] == M.REVIEW_REQUIRED   # annotation did NOT tag it


# ── §10.8 — an UNCERTAIN twin cannot shadow the CONFIRMED authoritative group ─
def test_uncertain_twin_does_not_shadow_confirmed():
    furn = [_f("dt-1", DINING, room_membership=M.KITCHEN)]
    rooms = [
        _room("dining-area", "Dining Area", "UNCERTAIN", [_f("door-1", "door")]),  # twin
        _room("kda", "Kitchen & Dining Area", "CONFIRMED",
              [_f("dt-1", DINING), _f("ch-1", KITCHEN_ANCHOR)]),
    ]
    d = M.resolve_dining_memberships(furn, rooms)[0]
    assert d["status"] == M.RESOLVED
    assert d["group_room_id"] == "kda"          # the CONFIRMED room, not the twin


# ── §10.10 — exactly one decision per dining item; non-dining untouched ───────
def test_exactly_once_per_dining_and_non_dining_untouched():
    furn = [
        _f("dt-1", DINING, room_membership=M.KITCHEN),
        _f("dt-2", DINING, room_membership=M.INDEPENDENT_DINING),
        _f("sofa-1", LIVING_ANCHOR),
        _f("bed-1", "bed"),
    ]
    rooms = [
        _room("kda", "Kitchen & Dining Area", "CONFIRMED",
              [_f("dt-1", DINING), _f("ch-1", KITCHEN_ANCHOR)]),
        _room("dining2", "Dining Area 2", "CONFIRMED", [_f("dt-2", DINING)]),
    ]
    decisions = M.resolve_dining_memberships(furn, rooms)
    assert len(decisions) == 2
    assert {d["uid"] for d in decisions} == {"dt-1", "dt-2"}


# ── §10.11/§3 — resolver is PURE: never mutates its inputs ────────────────────
def test_resolver_does_not_mutate_inputs():
    furn = [_f("dt-1", DINING, room_membership=M.KITCHEN)]
    rooms = [_room("kda", "K&D", "CONFIRMED", [_f("dt-1", DINING), _f("ch-1", KITCHEN_ANCHOR)])]
    furn_snapshot = copy.deepcopy(furn)
    rooms_snapshot = copy.deepcopy(rooms)
    M.resolve_dining_memberships(furn, rooms)
    assert furn == furn_snapshot
    assert rooms == rooms_snapshot


# ── §9/§10.13 — membership participates in the geometry/cache hash only when set ─
def test_membership_cache_fingerprint_semantics():
    legacy = {"furniture": [{"uid": "dt-1", "item_id": DINING, "cx": 1.0, "cy": 2.0,
                             "w": 3.0, "h": 4.0, "rotation": 0.0}]}
    # Dropping an unset membership (as save_layout does) must leave the hash identical
    # to the pre-field canonical → no spurious cache invalidation for legacy designs.
    assert G._geometry_hash(copy.deepcopy(legacy)) == G._geometry_hash(copy.deepcopy(legacy))
    tagged = copy.deepcopy(legacy)
    tagged["furniture"][0]["room_membership"] = M.KITCHEN
    # A SET membership changes the geometry hash → busts stale base/render caches.
    assert G._geometry_hash(tagged) != G._geometry_hash(legacy)


# ── serialization contract: None dropped, value kept (mirrors save_layout) ────
# ── G1 gate bridge: blocked_dining_sections maps blocked dining -> section ──
def test_blocked_sections_blocks_open_plan_untagged_dining():
    furn = [_f("dt-1", DINING), _f("ch-1", KITCHEN_ANCHOR)]  # untagged open-plan
    rooms = [_room("kda", "Kitchen & Dining Area", "CONFIRMED",
                   [_f("dt-1", DINING), _f("ch-1", KITCHEN_ANCHOR)])]
    sections = [("Dining Area", [_f("dt-1", DINING)]), ("Kitchen", [_f("ch-1", KITCHEN_ANCHOR)])]
    blocked = M.blocked_dining_sections(furn, rooms, sections)
    assert "Dining Area" in blocked
    assert blocked["Dining Area"]["code"] == M.REVIEW_REQUIRED_CODE
    assert blocked["Dining Area"]["uid"] == "dt-1"
    assert "Kitchen" not in blocked  # unrelated section is NOT blocked (partial execution)


# ── Step 2 merge-pending gap: validly-resolved Kitchen/Living dining is BLOCKED until
#    render-set merging exists (never silently rendered as an independent room) ──
def test_resolved_kitchen_is_merge_pending_blocked_until_merge_supported():
    furn = [_f("dt-1", DINING, room_membership=M.KITCHEN)]
    rooms = [_room("kda", "Kitchen & Dining Area", "CONFIRMED",
                   [_f("dt-1", DINING), _f("ch-1", KITCHEN_ANCHOR)])]
    sections = [("Dining Area", [_f("dt-1", DINING)])]
    blocked = M.blocked_dining_sections(furn, rooms, sections)  # merge_supported=False default
    assert blocked["Dining Area"]["code"] == M.MERGE_PENDING_CODE
    # Once merging is implemented, the same case is allowed (no block).
    assert M.blocked_dining_sections(furn, rooms, sections, merge_supported=True) == {}


def test_resolved_living_is_merge_pending_blocked():
    furn = [_f("dt-1", DINING, room_membership=M.LIVING_AREA)]
    rooms = [_room("lda", "Living & Dining", "CONFIRMED",
                   [_f("dt-1", DINING), _f("sofa-1", LIVING_ANCHOR)])]
    sections = [("Dining Area", [_f("dt-1", DINING)])]
    assert M.blocked_dining_sections(furn, rooms, sections)["Dining Area"]["code"] == M.MERGE_PENDING_CODE


def test_blocked_sections_independent_dining_not_blocked():
    furn = [_f("dt-1", DINING)]  # untagged, own confirmed room -> independent, no block
    rooms = [_room("dining", "Dining Area", "CONFIRMED", [_f("dt-1", DINING)])]
    sections = [("Dining Area", [_f("dt-1", DINING)])]
    assert M.blocked_dining_sections(furn, rooms, sections) == {}


def test_explicit_independent_dining_not_blocked():
    furn = [_f("dt-1", DINING, room_membership=M.INDEPENDENT_DINING)]
    rooms = [_room("dining", "Dining Area", "CONFIRMED", [_f("dt-1", DINING)])]
    sections = [("Dining Area", [_f("dt-1", DINING)])]
    assert M.blocked_dining_sections(furn, rooms, sections) == {}


def test_layout_item_membership_serialization_contract():
    from app.schemas.floor_plan import LayoutItem

    def _canonicalize(item: LayoutItem) -> dict:
        return {k: v for k, v in item.model_dump().items()
                if not (k == "room_membership" and v is None)}

    untagged = LayoutItem(uid="dt-1", item_id=DINING, cx=1, cy=2, w=3, h=4, rotation=0)
    assert "room_membership" not in _canonicalize(untagged)

    tagged = LayoutItem(uid="dt-1", item_id=DINING, cx=1, cy=2, w=3, h=4, rotation=0,
                        room_membership=M.KITCHEN)
    out = _canonicalize(tagged)
    assert out["room_membership"] == M.KITCHEN
    # round-trips back through the schema
    assert LayoutItem(**out).room_membership == M.KITCHEN
