"""Annotation-exclusion contract (`room-tag`), kept separate from the geometry baseline.

The frozen v31 geometry fixture intentionally has **zero** annotations, so the invariant
"every canonical item appears in the 3D scene" holds there. Annotations are a distinct,
later editor concept: a ``room-tag`` is a label the user drops on the plan, NOT furniture.
It must be classified as an annotation, excluded from furniture grouping, and must never
become a 3D scene object or be counted as real furniture. These focused tests lock that
behaviour directly (this is exactly what made the live-data invariant tests fail once the
real design gained 5 ``room-tag`` annotations — the scene correctly excluded them).
"""

import copy

from app.data import furniture_catalog
from app.services import prompt_service, scene_service

FID = "f6b65d2b-4f96-4931-9f08-67dbd09776f6"


def _item(uid, item_id, cx, cy, w=150, h=200):
    return {"uid": uid, "item_id": item_id, "cx": cx, "cy": cy, "w": w, "h": h, "rotation": 0}


def test_room_tag_is_classified_as_annotation():
    assert furniture_catalog.is_annotation("room-tag") is True
    assert "room-tag" in furniture_catalog.ANNOTATION_IDS
    # real furniture and openings are NOT annotations
    assert furniture_catalog.is_annotation("bed") is False
    assert furniture_catalog.is_annotation("door") is False
    assert furniture_catalog.is_annotation("window") is False


def test_strip_annotations_removes_only_room_tags():
    furn = [_item("b1", "bed", 100, 100),
            _item("t1", "room-tag", 110, 110, w=600, h=300),
            _item("d1", "door", 120, 120),
            _item("w1", "window", 130, 130)]
    kept = furniture_catalog.strip_annotations(furn)
    ids = [str(f["item_id"]) for f in kept]
    assert "room-tag" not in ids
    assert ids == ["bed", "door", "window"]  # openings are preserved, not stripped


def test_group_by_room_never_emits_an_annotation():
    # A bed seeds a room; a room-tag sitting right next to it must NOT be grouped as
    # furniture (it is stripped before clustering), so no section ever lists it.
    furn = [_item("b1", "bed", 100, 100),
            _item("t1", "room-tag", 110, 110, w=600, h=300)]
    groups = prompt_service.group_by_room(furn)
    emitted = [str(i["item_id"]) for _label, items in groups for i in items]
    assert "bed" in emitted
    assert "room-tag" not in emitted


def test_annotations_excluded_from_scene_but_present_in_canonical(frozen_v31):
    # Augment the frozen v31 canonical (0 annotations) with synthetic room-tags, then
    # build the scene from it: the annotations stay in the canonical but NEVER become
    # scene furniture, and the real inventory count is unchanged. This reproduces and
    # locks the exact contract the live-data drift exercised.
    aug = copy.deepcopy(frozen_v31)
    base_n = len(aug["furniture"])
    for i in range(3):
        aug["furniture"].append(_item(f"room-tag-synthetic-{i}", "room-tag",
                                       600 + i, 600 + i, w=600, h=300))
    assert len(aug["furniture"]) == base_n + 3  # annotations ARE in the canonical

    scene = scene_service.build_scene(FID, canonical=aug)
    scene_items = [f for r in scene["rooms"] for f in r["furniture"]]
    scene_item_ids = {str(f["item_id"]) for f in scene_items}
    assert "room-tag" not in scene_item_ids           # excluded from the 3D scene
    assert len(scene_items) == base_n                  # real inventory unchanged (34)
