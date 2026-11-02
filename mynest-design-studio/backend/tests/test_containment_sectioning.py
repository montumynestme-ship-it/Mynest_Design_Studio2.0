"""Phase 4C Step 2P — containment-aware sectioning (offline, no DB writes).

group_by_room defers to AUTHORITATIVE CONFIRMED-room containment (via containment_map)
instead of nearest-seed proximity, fixing section<->scene disagreements like a wardrobe
geometrically inside Bedroom 3 but nearest Bedroom 1's bed. Backward compatible: no map
(or no walls) -> unchanged nearest-seed behavior.
"""
from __future__ import annotations

import copy

from app.services import prompt_service as P


def _f(uid, item_id, cx, cy, w=50.0, h=50.0):
    return {"uid": uid, "item_id": item_id, "cx": cx, "cy": cy, "w": w, "h": h, "rotation": 0.0}


def _bucket_label_of(groups, uid):
    for label, items in groups:
        if any(str(i.get("uid")) == uid for i in items):
            return label
    return None


# ── group_by_room containment override ────────────────────────────────────────

def test_nearest_seed_is_default_without_containment():
    bedA = _f("bedA", "bed", 100, 100)
    bedB = _f("bedB", "bed", 900, 900)
    ward = _f("ward", "wardrobe", 160, 160)  # nearest bedA
    groups = P.group_by_room([bedA, bedB, ward])
    # wardrobe clusters with the nearest bed (bedA's bucket)
    assert _bucket_label_of(groups, "ward") == _bucket_label_of(groups, "bedA")


def test_containment_overrides_nearest_seed():
    bedA = _f("bedA", "bed", 100, 100)
    bedB = _f("bedB", "bed", 900, 900)
    ward = _f("ward", "wardrobe", 160, 160)  # nearest bedA, but containment says bedB's room
    groups = P.group_by_room([bedA, bedB, ward], None, {"ward": "bedB"})
    assert _bucket_label_of(groups, "ward") == _bucket_label_of(groups, "bedB")
    assert _bucket_label_of(groups, "ward") != _bucket_label_of(groups, "bedA")


def test_containment_noop_when_item_already_with_its_seed():
    bedA = _f("bedA", "bed", 100, 100)
    ward = _f("ward", "wardrobe", 160, 160)
    g_plain = P.group_by_room([bedA, ward])
    g_map = P.group_by_room([bedA, ward], None, {"ward": "bedA"})
    assert _bucket_label_of(g_plain, "ward") == _bucket_label_of(g_map, "ward")


def test_containment_map_unknown_seed_falls_back():
    bedA = _f("bedA", "bed", 100, 100)
    ward = _f("ward", "wardrobe", 160, 160)
    # target seed uid does not exist among seeds -> fall back to nearest (no crash)
    groups = P.group_by_room([bedA, ward], None, {"ward": "nonexistent"})
    assert _bucket_label_of(groups, "ward") == _bucket_label_of(groups, "bedA")


# ── build_section_containment_map ─────────────────────────────────────────────

def _room(rid, items, status="CONFIRMED", label=None):
    return {"id": rid, "label": label or rid, "validation_status": status, "furniture": items}


def test_build_map_maps_contained_items_to_room_seed():
    rooms = [
        _room("b1", [_f("bedA", "bed", 100, 100), _f("w1", "wardrobe", 120, 120)], label="Bedroom 1"),
        _room("b3", [_f("bedB", "bed", 900, 900), _f("w2", "wardrobe", 920, 920)], label="Bedroom 3"),
    ]
    m = P.build_section_containment_map(rooms)
    assert m == {"w1": "bedA", "w2": "bedB"}


def test_build_map_skips_uncertain_combined_and_seedless():
    rooms = [
        _room("u", [_f("bedA", "bed", 1, 1), _f("w", "wardrobe", 2, 2)], status="UNCERTAIN"),
        _room("kd", [_f("chim", "chimney", 1, 1), _f("dt", "dining-table", 2, 2)], label="Kitchen & Dining Area"),
        _room("noSeed", [_f("w2", "wardrobe", 3, 3)], label="Store"),
    ]
    assert P.build_section_containment_map(rooms) == {}  # none qualify


def test_build_map_excludes_dining_seed():
    rooms = [_room("b", [_f("bedA", "bed", 1, 1), _f("dt", "dining-table", 2, 2)], label="Bedroom 1")]
    # dining is reconciled by merge_map, never by containment
    assert "dt" not in P.build_section_containment_map(rooms)


# ── real v79 integration (READ-ONLY) ──────────────────────────────────────────

def test_v79_wardrobe_sections_to_bedroom3_and_gate_matches():
    import pytest
    from app.services import floor_plan_service, scene_service, furniture_manifest, base_inventory_service

    FID = "f6b65d2b-4f96-4931-9f08-67dbd09776f6"
    WARD = "wardrobe-1787646606853"
    try:
        _vid, _n, canon = floor_plan_service.capture_generation_snapshot(FID)
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"snapshot unavailable: {exc}")

    furn = canon.get("furniture", []) or []
    before_tx = {str(f["uid"]): (f["cx"], f["cy"], f["w"], f["h"], f["rotation"]) for f in furn}
    scene = scene_service.build_scene(FID, canonical=canon)
    rooms = scene["rooms"]
    cmap = P.build_section_containment_map(rooms)

    def section_of(uid, containment):
        for label, items in P.group_by_room(furn, None, containment):
            if any(str(i.get("uid")) == uid for i in items):
                return label
        return None

    assert section_of(WARD, None) == "Bedroom 1"      # the defect
    assert section_of(WARD, cmap) == "Bedroom 3"       # fixed: matches authoritative geometry

    # Bedroom 1 inventory gate: MISMATCH before, MATCH after (no phantom wardrobe prompted)
    def gate(label, containment):
        man = furniture_manifest.room_manifest(canon, label, None, containment)
        norm = P._normalize_section_name(label)
        base = next((r for r in rooms
                     if P._normalize_section_name(str(r.get("label", ""))) == norm
                     and str(r.get("validation_status", "")).upper() == "CONFIRMED"), None)
        return base_inventory_service.assess_section_base_inventory(man, base, rooms)[0]

    assert gate("Bedroom 1", None) == "MISMATCH"
    assert gate("Bedroom 1", cmap) == "MATCH"
    assert gate("Bedroom 3", cmap) == "MATCH"

    # canonical transforms unchanged; exactly-once across sections
    after_tx = {str(f["uid"]): (f["cx"], f["cy"], f["w"], f["h"], f["rotation"]) for f in canon.get("furniture", [])}
    assert after_tx == before_tx
    from collections import Counter
    cnt = Counter(str(i.get("uid")) for _l, items in P.group_by_room(furn, None, cmap) for i in items)
    assert not [u for u, c in cnt.items() if c > 1]
