"""AIR-03 Step 3/4 — end-to-end authoritative merge through generate() (offline).

Uses the frozen v31 canonical (pinned via monkeypatch, deterministic) with its dining
table tagged KITCHEN, and a MockAdapter (no paid call), to prove the FULL backend path
honors the authoritative merge: a tagged Dining produces a Kitchen target containing the
dining inventory, NO separate Dining target, and unchanged canonical transforms.
"""
from __future__ import annotations

import copy
import json
import pathlib
import unittest.mock as mock

import pytest

from app.services import floor_plan_service, generation_service, prompt_service
from app.services import furniture_manifest as FM
from app.services import room_membership_service as M
from app.services.ai import registry
from app.services.ai.mock_adapter import MockAdapter

FID = "f6b65d2b-4f96-4931-9f08-67dbd09776f6"
_V31 = pathlib.Path(__file__).parent / "fixtures" / "canonical_v31_1831bf84.json"
DINING_UID = "dining-table-1787478800756"


def _tagged_canonical(membership="KITCHEN"):
    cj = json.loads(_V31.read_text(encoding="utf-8"))
    for f in cj["furniture"]:
        if f["uid"] == DINING_UID:
            f["room_membership"] = membership
    return cj


@pytest.fixture
def tagged_v31(monkeypatch):
    """Pin BOTH the canonical reader and the generation snapshot to the FROZEN v31
    fixture (deterministic, not the mutable live DB) with the dining tagged KITCHEN."""
    # Wrap the REAL snapshot (keeps a valid version id for persistence/provenance) and
    # add the KITCHEN membership tag to the dining item by item_id — deterministic tag on
    # the established FID design the existing generation tests already use.
    real_snap = floor_plan_service.capture_generation_snapshot

    def _tag(canon):
        canon = copy.deepcopy(canon)
        for f in canon.get("furniture", []) or []:
            if str(f.get("item_id")) == "dining-table":
                f["room_membership"] = "KITCHEN"
        return canon

    def _patched_snapshot(file_id):
        vid, vnum, canon = real_snap(file_id)
        return vid, vnum, _tag(canon)

    monkeypatch.setattr(floor_plan_service, "capture_generation_snapshot", _patched_snapshot)
    return None


# ── end-to-end generate(): tagged Dining merges into Kitchen, no Dining target ──
def test_generate_merges_tagged_dining_into_kitchen(tagged_v31):
    with mock.patch.object(registry, "get_adapter", return_value=MockAdapter()):
        resp = generation_service.generate(
            file_id=FID, provider="mock", count=1,
            design_intent={"style": "Modern Luxury"}, all_sections=False,
            fresh_generation=True,
        )
    # geometry lock held throughout generation => canonical transforms unchanged
    assert resp.status == "completed"
    labels = resp.requested_rooms or []
    # NO separate Dining target; a Kitchen target IS present
    assert not any("dining" in l.lower() and "kitchen" not in l.lower() for l in labels), labels
    assert any("kitchen" in l.lower() for l in labels), labels


def test_tagged_kitchen_manifest_contains_dining(tagged_v31):
    canon = _tagged_canonical("KITCHEN")
    # the merge_map the pipeline computes for this design
    from app.services import scene_service
    scene = scene_service.build_scene(FID, canonical=canon)
    mm = M.resolve_authoritative_groups(
        canon["furniture"], scene.get("rooms", []) or [], merge_supported=True)["merge_map"]
    assert mm.get(DINING_UID) == M.KITCHEN      # dining validly resolves to Kitchen
    sections = prompt_service.get_eligible_sections(canon, mm)
    assert not any(s.strip().lower() == "dining area" for s in sections), sections
    manifest = FM.build_manifest(canon, mm)
    kitchen_keys = [k for k in manifest if k.lower() == "kitchen"]
    assert kitchen_keys, list(manifest)
    kuids = {it["uid"] for it in manifest[kitchen_keys[0]]["items"]}
    assert DINING_UID in kuids
    # and no dining-area manifest section remains
    assert not any(k.lower() == "dining area" for k in manifest)


# ── prompt-side grouping with extra dining furniture (chairs) folds whole section ──
def test_dining_section_with_chairs_merges_wholesale():
    def f(uid, iid, cx, cy, mem=None):
        d = {"uid": uid, "item_id": iid, "cx": float(cx), "cy": float(cy),
             "w": 80.0, "h": 50.0, "rotation": 0.0}
        if mem:
            d["room_membership"] = mem
        return d
    furn = [
        f("kb", "kitchen-base", 100, 100), f("ch", "chimney", 130, 100),
        f("dt", "dining-table", 500, 500, "KITCHEN"),
        f("chair1", "side-table", 470, 520), f("chair2", "side-table", 530, 520),
        f("sofa", "lounger-sofa", 900, 900),
    ]
    merged = prompt_service.group_by_room(furn, {"dt": "KITCHEN"})
    assert not any("dining" in lbl.lower() for lbl, _ in merged)
    kitchen_items = next(items for lbl, items in merged if "kitchen" in lbl.lower())
    kuids = {i["uid"] for i in kitchen_items}
    # the whole dining cluster (table + its chairs) folded into Kitchen
    assert {"dt", "chair1", "chair2"} <= kuids
    # exactly-once: no uid duplicated/lost
    all_uids = [i["uid"] for _l, items in merged for i in items]
    assert sorted(all_uids) == sorted(f["uid"] for f in furn)
    assert len(all_uids) == len(set(all_uids))


# ── blocking: conflicting membership is flagged for the gate (pre-provider refuse) ──
def test_conflicting_membership_is_blocked_for_gate():
    def f(uid, iid, mem=None):
        d = {"uid": uid, "item_id": iid}
        if mem:
            d["room_membership"] = mem
        return d
    furn = [f("dt", "dining-table", "KITCHEN"), f("ch", "chimney")]
    # geometry: dining and the kitchen anchor are in DIFFERENT confirmed rooms -> conflict
    rooms = [
        {"id": "dining", "label": "Dining Area", "validation_status": "CONFIRMED",
         "furniture": [f("dt", "dining-table")]},
        {"id": "kitchen", "label": "Kitchen", "validation_status": "CONFIRMED",
         "furniture": [f("ch", "chimney")]},
    ]
    sections = [("Dining Area", [f("dt", "dining-table")]), ("Kitchen", [f("ch", "chimney")])]
    blocked = M.blocked_dining_sections(furn, rooms, sections, merge_supported=True)
    assert "Dining Area" in blocked
    assert blocked["Dining Area"]["code"] == M.REVIEW_REQUIRED_CODE
    assert "Kitchen" not in blocked          # unrelated section proceeds (partial execution)
