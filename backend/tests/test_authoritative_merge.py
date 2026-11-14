"""AIR-03 Step 3 — authoritative render-set merge (offline, deterministic, synthetic).

Verifies that a validly-assigned Kitchen/Living dining is folded into one destination
group consistently across group_by_room, eligibility, manifest and the scene twin-drop,
with furniture transforms unchanged and no item duplicated or lost. No DB, no provider,
no real design, no hardcoded coordinates beyond what the synthetic cluster needs.
"""
from __future__ import annotations

import copy

from app.services import prompt_service as P
from app.services import furniture_manifest as FM
from app.services import room_membership_service as M
from app.services import scene_service as S

DINING = "dining-table"
KITCHEN_ANCHOR = "chimney"       # ∈ _KITCHEN_IDS
LIVING_ANCHOR = "lounger-sofa"   # ∈ _SOFAS


def _f(uid, item_id, cx, cy, **extra):
    return {"uid": uid, "item_id": item_id, "cx": float(cx), "cy": float(cy),
            "w": 100.0, "h": 60.0, "rotation": 0.0, **extra}


def _clustered_furniture(dining_membership=None):
    # three spatial clusters so group_by_room yields Kitchen + Dining + Living sections
    dt = _f("dt-1", DINING, 500, 500)
    if dining_membership:
        dt["room_membership"] = dining_membership
    return [
        _f("kb-1", "kitchen-base", 100, 100),
        _f("ch-1", KITCHEN_ANCHOR, 130, 100),
        dt,
        _f("sofa-1", LIVING_ANCHOR, 900, 900),
    ]


def _room(rid, label, status, furn):
    return {"id": rid, "label": label, "validation_status": status, "furniture": furn}


# ── group_by_room merge: Dining folded into Kitchen; nothing duplicated or lost ──
def test_group_by_room_merges_dining_into_kitchen():
    furn = _clustered_furniture(M.KITCHEN)
    base = P.group_by_room(furn)                      # no merge -> separate Dining
    base_labels = {lbl for lbl, _ in base}
    assert any("Dining" in l for l in base_labels)     # precondition: Dining exists

    merged = P.group_by_room(furn, {"dt-1": M.KITCHEN})
    merged_labels = {lbl for lbl, _ in merged}
    assert not any("Dining" in l for l in merged_labels)   # Dining section gone
    # dining item now lives in the Kitchen section
    kitchen_items = next(items for lbl, items in merged if "Kitchen" in lbl)
    assert any(i["uid"] == "dt-1" for i in kitchen_items)
    # exactly-once: every uid preserved across the merge, none duplicated
    def _uids(groups):
        out = []
        for _l, items in groups:
            out += [i["uid"] for i in items]
        return out
    assert sorted(_uids(merged)) == sorted(_uids(base))
    assert len(_uids(merged)) == len(set(_uids(merged)))


def test_group_by_room_merge_preserves_transforms():
    furn = _clustered_furniture(M.KITCHEN)
    before = {f["uid"]: (f["cx"], f["cy"], f["w"], f["h"], f["rotation"]) for f in furn}
    merged = P.group_by_room(furn, {"dt-1": M.KITCHEN})
    for _l, items in merged:
        for i in items:
            assert (i["cx"], i["cy"], i["w"], i["h"], i["rotation"]) == before[i["uid"]]


def test_group_by_room_living_merge():
    furn = _clustered_furniture(M.LIVING_AREA)
    merged = P.group_by_room(furn, {"dt-1": M.LIVING_AREA})
    assert not any("Dining" in lbl for lbl, _ in merged)
    living_items = next(items for lbl, items in merged if "Living" in lbl)
    assert any(i["uid"] == "dt-1" for i in living_items)


def test_no_merge_map_is_legacy_behavior():
    furn = _clustered_furniture(M.KITCHEN)
    assert P.group_by_room(furn, None) == P.group_by_room(furn)
    assert any("Dining" in lbl for lbl, _ in P.group_by_room(furn, {}))


# ── resolve_authoritative_groups: merge_map only when resolved + merge_supported ──
def test_resolve_authoritative_groups_merge_map():
    furn = _clustered_furniture(M.KITCHEN)
    rooms = [_room("kda", "Kitchen & Dining Area", "CONFIRMED",
                   [_f("dt-1", DINING, 500, 500), _f("ch-1", KITCHEN_ANCHOR, 130, 100)])]
    got = M.resolve_authoritative_groups(furn, rooms, merge_supported=True)
    assert got["merge_map"] == {"dt-1": M.KITCHEN}
    # merge NOT supported -> empty map (gate keeps it merge-pending instead)
    assert M.resolve_authoritative_groups(furn, rooms, merge_supported=False)["merge_map"] == {}


def test_resolve_authoritative_groups_untagged_is_empty():
    furn = _clustered_furniture(None)  # untagged
    rooms = [_room("kda", "Kitchen & Dining Area", "CONFIRMED",
                   [_f("dt-1", DINING, 500, 500), _f("ch-1", KITCHEN_ANCHOR, 130, 100)])]
    assert M.resolve_authoritative_groups(furn, rooms, merge_supported=True)["merge_map"] == {}


# ── eligibility + manifest consume the SAME grouping ──
def test_eligibility_and_manifest_agree_under_merge():
    canonical = {"furniture": _clustered_furniture(M.KITCHEN)}
    mm = {"dt-1": M.KITCHEN}
    sections = P.get_eligible_sections(canonical, mm)
    assert not any("Dining" in s for s in sections)        # no separate Dining section
    manifest = FM.build_manifest(canonical, mm)
    # the dining item's section is Kitchen in the manifest too (consistent grouping)
    kitchen_key = next(k for k in manifest if k.lower() == "kitchen")
    kitchen_uids = {it["uid"] for it in manifest[kitchen_key]["items"]}
    assert "dt-1" in kitchen_uids
    assert not any("dining" in k.lower() for k in manifest)


# ── scene twin-drop: UNCERTAIN dining twin dropped; CONFIRMED kept; transforms intact ──
def test_scene_drops_only_redundant_uncertain_dining_twin():
    kda = _room("kda", "Kitchen & Dining Area", "CONFIRMED",
                [_f("dt-1", DINING, 500, 500), _f("ch-1", KITCHEN_ANCHOR, 130, 100)])
    twin = _room("dining-area", "Dining Area", "UNCERTAIN", [_f("door-1", "door", 480, 520)])
    living = _room("living", "Living Area", "CONFIRMED", [_f("sofa-1", LIVING_ANCHOR, 900, 900)])
    rooms = [kda, twin, living]
    before = copy.deepcopy(rooms)
    kept = S._drop_merged_dining_twins(rooms, {"dt-1": M.KITCHEN})
    kept_ids = {r["id"] for r in kept}
    assert "dining-area" not in kept_ids        # redundant twin dropped
    assert {"kda", "living"} <= kept_ids         # CONFIRMED rooms kept
    # the destination CONFIRMED room still carries the dining item at its transform
    kept_kda = next(r for r in kept if r["id"] == "kda")
    dt = next(f for f in kept_kda["furniture"] if f["uid"] == "dt-1")
    assert (dt["cx"], dt["cy"], dt["rotation"]) == (500.0, 500.0, 0.0)
    # empty merge_map leaves the scene identical (legacy/untagged safety)
    assert S._drop_merged_dining_twins(copy.deepcopy(before), {}) == before


def test_scene_never_drops_confirmed_or_anchored_dining():
    # a CONFIRMED dining room, or one holding a kitchen/living anchor, is NEVER dropped
    confirmed_dining = _room("d", "Dining Area", "CONFIRMED", [_f("dt-1", DINING, 500, 500)])
    kept = S._drop_merged_dining_twins([confirmed_dining], {"dt-1": M.KITCHEN})
    assert len(kept) == 1
