"""Phase 4C Step 2M.1 — explicit render inclusion (offline, detector-free, no DB writes).

Covers the required cases:
  * explicit assignment distinguished from automatic inference (render_room vs geometry);
  * render inclusion does not alter canonical transforms / inventory; item appears once;
  * ordinary wall-adjacent furniture unaffected;
  * uncertain open-plan behavior unchanged unless explicitly selected;
  * missing / ambiguous / conflicting / invalid targets fail safe (no move);
  * dining items untouched by this resolver;
  * the real v79 kitchen-base case: tagging KITCHEN moves both units into the CONFIRMED
    room exactly once (render_inclusion flag) and flips the Kitchen inventory gate MATCH,
    with canonical transforms byte-identical.
"""
from __future__ import annotations

import copy

from app.services import room_membership_service as M


def _f(uid, item_id, **kw):
    d = {"uid": uid, "item_id": item_id, "cx": 0.0, "cy": 0.0, "w": 1.0, "h": 1.0, "rotation": 0.0}
    d.update(kw)
    return d


def _room(rid, items, status="CONFIRMED", label=None):
    return {"id": rid, "label": label or rid, "validation_status": status, "furniture": items}


# ── resolver ────────────────────────────────────────────────────────────────

def test_resolve_moves_outofroom_item_to_unique_confirmed_kitchen():
    base = _f("kb-1", "kitchen-base", render_room="KITCHEN")
    rooms = [
        _room("kitchen", [_f("chim-1", "chimney")], status="CONFIRMED"),          # KITCHEN anchor
        _room("kitchen-2", [base], status="UNCERTAIN"),                            # the stray base unit
    ]
    out = M.resolve_render_inclusions([base, _f("chim-1", "chimney")], rooms)
    assert out["inclusion_map"] == {"kb-1": "kitchen"}
    d = out["decisions"][0]
    assert d["status"] == M.RESOLVED and d["move"] is True


def test_resolve_ambiguous_two_confirmed_kitchens_is_review_no_move():
    base = _f("kb-1", "kitchen-base", render_room="KITCHEN")
    rooms = [
        _room("k1", [_f("chim-1", "chimney")], status="CONFIRMED"),
        _room("k2", [_f("cook-1", "cooktop")], status="CONFIRMED"),
        _room("u", [base], status="UNCERTAIN"),
    ]
    out = M.resolve_render_inclusions([base], rooms)
    assert out["inclusion_map"] == {}
    assert "AMBIGUOUS_DESTINATION" in out["decisions"][0]["reason"]


def test_resolve_no_confirmed_target_is_review():
    base = _f("kb-1", "kitchen-base", render_room="KITCHEN")
    rooms = [_room("u", [base], status="UNCERTAIN")]
    out = M.resolve_render_inclusions([base], rooms)
    assert out["inclusion_map"] == {}
    assert "INSUFFICIENT_EVIDENCE" in out["decisions"][0]["reason"]


def test_resolve_conflict_with_confirmed_containment_does_not_override():
    # item is already contained in a DIFFERENT confirmed room -> never override geometry.
    # Use a console (a living-room item, NOT a kitchen anchor) tagged KITCHEN but firmly
    # contained in the CONFIRMED living room.
    item = _f("c-1", "console", render_room="KITCHEN")
    rooms = [
        _room("kitchen", [_f("chim-1", "chimney")], status="CONFIRMED"),
        _room("living", [item], status="CONFIRMED"),  # console firmly here by geometry
    ]
    out = M.resolve_render_inclusions([item], rooms)
    assert out["inclusion_map"] == {}
    assert "CONFLICT" in out["decisions"][0]["reason"]


def test_resolve_already_in_target_is_noop_resolved():
    base = _f("kb-1", "kitchen-base", render_room="KITCHEN")
    rooms = [_room("kitchen", [base, _f("chim-1", "chimney")], status="CONFIRMED")]
    out = M.resolve_render_inclusions([base], rooms)
    assert out["inclusion_map"] == {}  # already there -> no move
    assert out["decisions"][0]["status"] == M.RESOLVED


def test_resolve_invalid_token_is_review():
    base = _f("kb-1", "kitchen-base", render_room="BATHROOM")
    rooms = [_room("kitchen", [_f("chim-1", "chimney")], status="CONFIRMED"), _room("u", [base], "UNCERTAIN")]
    out = M.resolve_render_inclusions([base], rooms)
    assert out["inclusion_map"] == {}
    assert "INVALID_RENDER_ROOM" in out["decisions"][0]["reason"]


def test_resolve_ignores_dining_items():
    # dining carries room_membership, not render_room; this resolver must skip dining seeds
    dt = _f("dt-1", "dining-table", render_room="KITCHEN")
    rooms = [_room("kitchen", [_f("chim-1", "chimney")], "CONFIRMED"), _room("u", [dt], "UNCERTAIN")]
    out = M.resolve_render_inclusions([dt], rooms)
    assert out["inclusion_map"] == {} and out["decisions"] == []


# ── scene application ─────────────────────────────────────────────────────────

def test_apply_moves_exactly_once_and_drops_emptied_uncertain_room():
    from app.services import scene_service as S
    base = _f("kb-1", "kitchen-base")
    rooms = [
        _room("kitchen", [_f("chim-1", "chimney")], status="CONFIRMED"),
        _room("kitchen-2", [base], status="UNCERTAIN"),
    ]
    kept = S._apply_render_inclusions(rooms, {"kb-1": "kitchen"})
    ids = [r["id"] for r in kept]
    assert "kitchen-2" not in ids            # emptied UNCERTAIN room dropped
    kroom = next(r for r in kept if r["id"] == "kitchen")
    kb = [f for f in kroom["furniture"] if f["uid"] == "kb-1"]
    assert len(kb) == 1 and kb[0]["render_inclusion"] is True
    assert kroom["furniture_count"] == len(kroom["furniture"])
    # exactly once across the whole scene
    total = sum(1 for r in kept for f in r["furniture"] if f["uid"] == "kb-1")
    assert total == 1


def test_apply_missing_target_is_noop():
    from app.services import scene_service as S
    base = _f("kb-1", "kitchen-base")
    rooms = [_room("u", [base], status="UNCERTAIN")]
    kept = S._apply_render_inclusions(rooms, {"kb-1": "nonexistent"})
    assert any(f["uid"] == "kb-1" for r in kept for f in r["furniture"])  # stays put


# ── real design integration (READ-ONLY; no DB writes) ─────────────────────────

def test_v79_tagging_kitchen_bases_includes_them_and_flips_gate_to_match():
    import pytest
    from app.services import (
        floor_plan_service, scene_service, prompt_service, furniture_manifest,
        base_inventory_service,
    )

    FID = "f6b65d2b-4f96-4931-9f08-67dbd09776f6"
    BASES = {"kitchen-base-1787478607029", "kitchen-base-1787478608231"}
    try:
        _vid, _n, canon = floor_plan_service.capture_generation_snapshot(FID)
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"target snapshot unavailable: {exc}")

    # Baseline (untagged): Kitchen gate is MISMATCH.
    base_scene = scene_service.build_scene(FID, canonical=canon)

    # Tag the two base units render_room=KITCHEN (IN-MEMORY canonical only; no persistence).
    tagged = copy.deepcopy(canon)
    orig_tx = {}
    for f in tagged.get("furniture", []):
        if str(f.get("uid")) in BASES:
            f["render_room"] = "KITCHEN"
            orig_tx[f["uid"]] = (f["cx"], f["cy"], f["w"], f["h"], f["rotation"], f["item_id"])
    scene = scene_service.build_scene(FID, canonical=tagged)
    rooms = scene["rooms"]

    # 1) Both base units are now in the CONFIRMED Kitchen & Dining room, flagged, EXACTLY once.
    kroom = next(r for r in rooms
                 if str(r.get("validation_status", "")).upper() == "CONFIRMED"
                 and any(str(f.get("uid")) == "chimney-1787478686293" for f in r["furniture"]))
    kuids = {str(f["uid"]) for f in kroom["furniture"]}
    assert BASES <= kuids, kuids
    for f in kroom["furniture"]:
        if str(f["uid"]) in BASES:
            assert f.get("render_inclusion") is True
    for uid in BASES:
        total = sum(1 for r in rooms for f in r["furniture"] if str(f.get("uid")) == uid)
        assert total == 1, (uid, total)

    # 2) Canonical transforms unchanged by the move.
    for f in kroom["furniture"]:
        if str(f["uid"]) in BASES:
            cx, cy, w, h, rot, iid = orig_tx[f["uid"]]
            assert (f["cx"], f["cy"], f["w"], f["h"], f["rotation"], f["item_id"]) == (cx, cy, w, h, rot, iid)

    # 3) The Kitchen inventory gate now MATCHes (base units present in the selected base room).
    mm = {}
    sections = prompt_service.group_by_room(tagged.get("furniture", []), mm)
    kitchen_items = next(items for lbl, items in sections if lbl.lower() == "kitchen")
    manifest = furniture_manifest.build_room_manifest(kitchen_items)
    st, why = base_inventory_service.assess_section_base_inventory(manifest, kroom, rooms)
    assert st == "MATCH", (st, why)


def test_v79_untagged_unchanged_bases_stay_uncertain():
    import pytest
    from app.services import floor_plan_service, scene_service

    FID = "f6b65d2b-4f96-4931-9f08-67dbd09776f6"
    BASES = {"kitchen-base-1787478607029", "kitchen-base-1787478608231"}
    try:
        _vid, _n, canon = floor_plan_service.capture_generation_snapshot(FID)
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"target snapshot unavailable: {exc}")
    scene = scene_service.build_scene(FID, canonical=canon)
    # untagged: no base unit carries render_inclusion, and none is in the CONFIRMED kitchen room
    for r in scene["rooms"]:
        for f in r["furniture"]:
            assert not f.get("render_inclusion")
    kconf = [r for r in scene["rooms"]
             if str(r.get("validation_status", "")).upper() == "CONFIRMED"
             and any(str(f.get("uid")) == "chimney-1787478686293" for f in r["furniture"])]
    assert kconf, "expected a CONFIRMED kitchen room with the chimney"
    kuids = {str(f["uid"]) for f in kconf[0]["furniture"]}
    assert not (BASES & kuids), "base units must NOT be in the confirmed room when untagged"
