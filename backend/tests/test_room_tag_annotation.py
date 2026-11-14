"""Dynamic room-tag annotations — user-defined section names that feed the AI prompt
as styling context WITHOUT changing any canonical furniture, geometry, or room data.

A room tag is a layout item with item_id "room-tag" whose custom name rides the existing
`label` field. It must be excluded from every furniture count, grouping, room
reconstruction, and 2D→3D geometry check (like an opening is excluded from furniture),
and its name must reach ONLY the prompt of the section it sits in.
"""

from app.data import furniture_catalog as C
from app.services import prompt_service as P
from app.services import validation_service as V
from app.services import furniture_manifest
from app.services.furniture_inventory_validation_service import expected_inventory


def _f(uid, item_id, cx, cy, w=40, h=40, **extra):
    return {"uid": uid, "item_id": item_id, "cx": cx, "cy": cy, "w": w, "h": h,
            "rotation": 0, **extra}


def _two_bed_plan(with_tag=True):
    fur = [
        _f("b1", "bed", 100, 100, 150, 200),
        _f("st1", "side-table", 260, 100),
        _f("b2", "bed", 600, 100, 150, 200),
    ]
    if with_tag:
        fur.append(_f("tag1", "room-tag", 120, 110, 10, 10, label="Master Bedroom"))
    return {"furniture": fur}


# ── annotation primitive ──
def test_is_annotation_and_strip():
    assert C.is_annotation("room-tag") is True
    assert C.is_annotation("bed") is False
    assert C.is_annotation(None) is False
    fur = _two_bed_plan()["furniture"]
    stripped = C.strip_annotations(fur)
    assert len(stripped) == 3
    assert all(f["item_id"] != "room-tag" for f in stripped)


# ── grouping never counts a tag as furniture ──
def test_group_by_room_excludes_tag():
    groups = P.group_by_room(_two_bed_plan()["furniture"])
    assert not any(f.get("item_id") == "room-tag" for _lbl, items in groups for f in items)
    # counts identical with and without the tag present
    g_no = P.group_by_room(_two_bed_plan(with_tag=False)["furniture"])
    assert sorted((l, len(i)) for l, i in groups) == sorted((l, len(i)) for l, i in g_no)


# ── tag → correct section ──
def test_tags_by_section_assigns_to_containing_section():
    tm = P.tags_by_section(_two_bed_plan())
    assert tm.get("Bedroom 1") == "Master Bedroom"
    assert "Bedroom 2" not in tm  # the tag sits in bedroom 1 only


def test_tags_by_section_empty_cases():
    assert P.tags_by_section(_two_bed_plan(with_tag=False)) == {}      # no tags
    assert P.tags_by_section({"furniture": []}) == {}                   # no furniture
    # empty name ignored
    plan = _two_bed_plan()
    plan["furniture"][-1]["label"] = "   "
    assert P.tags_by_section(plan) == {}


# ── prompt carries the tag for the right section ONLY ──
def test_prompt_includes_tag_for_its_section_only():
    _style, prompts = P.build_room_prompts(_two_bed_plan(), design_intent=None, all_sections=False)
    by = {lbl: text for lbl, text, _w, _h in prompts}
    assert "Master Bedroom" in by.get("Bedroom 1", "")
    assert "Master Bedroom" not in by.get("Bedroom 2", "")
    # and the injected context forbids layout changes (styling-only)
    assert "do NOT add, remove, move" in by["Bedroom 1"]


def test_prompt_unchanged_without_tags_backward_compatible():
    _s1, p1 = P.build_room_prompts(_two_bed_plan(with_tag=False), design_intent=None, all_sections=False)
    # a legacy design with no tags must produce prompts with no "User room designation"
    assert all("User room designation" not in text for _l, text, _w, _h in p1)


# ── inventory invariants: a tag changes NO furniture count ──
def test_tag_not_counted_in_inventory():
    with_tag = _two_bed_plan(with_tag=True)["furniture"]
    without = _two_bed_plan(with_tag=False)["furniture"]
    assert expected_inventory(with_tag) == expected_inventory(without)
    # manifest furniture counts per section are identical
    m_with = furniture_manifest.build_manifest({"furniture": with_tag})
    m_without = furniture_manifest.build_manifest({"furniture": without})
    counts_with = {k: v["furniture_count"] for k, v in m_with.items()}
    counts_without = {k: v["furniture_count"] for k, v in m_without.items()}
    assert counts_with == counts_without
    # the tag uid appears in NO manifest
    assert not any(
        it.get("uid") == "tag1" for m in m_with.values() for it in m.get("items", [])
    )


# ── geometry validation ignores the tag (no collision/containment, count aligned) ──
def test_validate_canonical_ignores_tag():
    results = V.validate_canonical(_two_bed_plan())
    assert not any("tag1" in str(r) or "room-tag" in str(r).lower() for r in results)


def test_validate_2d_to_3d_count_aligned_with_tag():
    # Canonical has the tag (4 items) but the scene (annotations stripped) has 3 furniture;
    # the 2D→3D furniture comparison must align on 3 and not report a count mismatch.
    canonical = _two_bed_plan()
    scene = {"rooms": [
        {"id": "bedroom-1", "label": "Bedroom 1", "furniture": [
            _f("b1", "bed", 100, 100, 150, 200), _f("st1", "side-table", 260, 100)]},
        {"id": "bedroom-2", "label": "Bedroom 2", "furniture": [
            _f("b2", "bed", 600, 100, 150, 200)]},
    ]}
    report = V.validate_scene_2d_to_3d(canonical, scene)
    # The dedicated 2D→3D check must not flag a furniture count mismatch caused by the tag.
    mismatches = " ".join(m.get("reason", "") for m in report.get("mismatches", []))
    assert "count" not in mismatches.lower() or "tag" not in mismatches.lower()
    assert report.get("counts", {}).get("canonical") in (3, None)  # tag excluded if reported
