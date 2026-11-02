"""Phase 4C Step 2O-A — full-design inventory reconciliation (offline, detector-free).

Proves the reconciliation makes a silent omission EXPLICIT:
  * canonical furniture dropped before scene construction (in a section, no scene room)
  * furniture omitted from every room payload / section
  * duplicate furniture uids
  * unknown furniture type (no catalog mapping)
  * openings and room-tag annotations are correctly EXCLUDED (not false positives)
  * the real target design (v79) reconciles cleanly: every real item accounted once.

No DB writes, no generation, no paid calls. The real-snapshot test is READ-ONLY.
"""
from __future__ import annotations

from app.services import inventory_reconciliation_service as R


def _f(uid, item_id, **kw):
    d = {"uid": uid, "item_id": item_id, "cx": 0.0, "cy": 0.0, "w": 1.0, "h": 1.0, "rotation": 0.0}
    d.update(kw)
    return d


def _room(label, items, status="CONFIRMED"):
    return {"id": label.lower(), "label": label, "validation_status": status, "items": items}


def test_all_accounted_is_ok():
    sofa = _f("sofa-1", "lounger-sofa")
    bed = _f("bed-1", "bed")
    furniture = [sofa, bed]
    sections = [("Living Area", [sofa]), ("Bedroom 1", [bed])]
    rooms = [_room("Living Area", [sofa]), _room("Bedroom 1", [bed])]
    res = R.reconcile_design_inventory(furniture, rooms, sections)
    assert res["ok"] is True, res
    assert res["real_count"] == 2
    assert R.reconciliation_warnings(res) == []


def test_openings_and_annotations_excluded_not_flagged():
    sofa = _f("sofa-1", "lounger-sofa")
    door = _f("door-1", "door")
    window = _f("win-1", "window")
    tag = _f("room-tag-1", "room-tag")
    furniture = [sofa, door, window, tag]
    sections = [("Living Area", [sofa])]  # openings/tag legitimately absent from sections
    rooms = [_room("Living Area", [sofa])]
    res = R.reconcile_design_inventory(furniture, rooms, sections)
    assert res["ok"] is True, res
    assert res["real_count"] == 1
    assert set(res["openings_excluded"]) == {"door-1", "win-1"}
    assert res["annotations_excluded"] == ["room-tag-1"]


def test_dropped_before_scene_construction_is_flagged():
    # In a section, but present in NO scene room -> would never render / be checked.
    sofa = _f("sofa-1", "lounger-sofa")
    ghost = _f("bed-1", "bed")
    furniture = [sofa, ghost]
    sections = [("Living Area", [sofa]), ("Bedroom 1", [ghost])]
    rooms = [_room("Living Area", [sofa])]  # Bedroom 1 missing entirely
    res = R.reconcile_design_inventory(furniture, rooms, sections)
    assert res["ok"] is False
    assert res["unaccounted_in_scene"] == ["bed-1"]
    assert any("NO scene room" in m for m in R.reconciliation_warnings(res))


def test_omitted_from_every_section_is_flagged():
    sofa = _f("sofa-1", "lounger-sofa")
    orphan = _f("bed-1", "bed")
    furniture = [sofa, orphan]
    sections = [("Living Area", [sofa])]  # orphan in no section
    rooms = [_room("Living Area", [sofa]), _room("Bedroom 1", [orphan])]
    res = R.reconcile_design_inventory(furniture, rooms, sections)
    assert res["ok"] is False
    assert res["unaccounted_in_sections"] == ["bed-1"]


def test_duplicate_uid_is_flagged():
    a = _f("dup-1", "lounger-sofa")
    b = _f("dup-1", "console")  # same uid reused
    furniture = [a, b]
    sections = [("Living Area", [a, b])]
    rooms = [_room("Living Area", [a, b])]
    res = R.reconcile_design_inventory(furniture, rooms, sections)
    assert res["ok"] is False
    assert res["duplicate_uids"] == ["dup-1"]


def test_unknown_type_is_flagged():
    weird = _f("x-1", "hovercraft")  # not in furniture_catalog.FURNITURE
    furniture = [weird]
    sections = [("Living Area", [weird])]
    rooms = [_room("Living Area", [weird])]
    res = R.reconcile_design_inventory(furniture, rooms, sections)
    assert res["ok"] is False
    assert res["unmapped_types"] == ["hovercraft"]


def test_uidless_real_furniture_is_flagged():
    furniture = [{"item_id": "bed", "cx": 0, "cy": 0, "w": 1, "h": 1, "rotation": 0}]
    res = R.reconcile_design_inventory(furniture, [], [])
    assert res["ok"] is False
    assert res["uidless"] == ["bed"]


def test_real_design_v79_reconciles_cleanly():
    """READ-ONLY: the live target design must reconcile with every real item accounted
    exactly once (openings + room-tags excluded, no duplicates, no unmapped types)."""
    import pytest

    from app.services import floor_plan_service, prompt_service, scene_service, room_membership_service

    FID = "f6b65d2b-4f96-4931-9f08-67dbd09776f6"
    try:
        _vid, _n, canon = floor_plan_service.capture_generation_snapshot(FID)
    except Exception as exc:  # pragma: no cover - DB/snapshot unavailable in some envs
        pytest.skip(f"target design snapshot unavailable: {exc}")

    furniture = canon.get("furniture", []) or []
    scene = scene_service.build_scene(FID, canonical=canon)
    rooms = scene.get("rooms", [])
    mm = room_membership_service.resolve_authoritative_groups(
        furniture, rooms, merge_supported=True
    )["merge_map"]
    sections = prompt_service.group_by_room(furniture, mm)

    res = R.reconcile_design_inventory(furniture, rooms, sections)
    assert res["ok"] is True, R.reconciliation_warnings(res)
    assert res["duplicate_uids"] == []
    assert res["unmapped_types"] == []
    assert res["unaccounted_in_sections"] == []
    assert res["unaccounted_in_scene"] == []
    # the 5 room-tag annotations are excluded, not treated as dropped furniture
    assert len(res["annotations_excluded"]) >= 1
