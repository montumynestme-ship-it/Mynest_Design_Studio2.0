"""Furniture-preservation pipeline: ONE manifest feeds prompt construction AND output
reconciliation (spec Stages C/D/E).

Offline only — no provider calls, no detector/OWLv2 weights, no DB writes, no paid API.
Proves:
  * the prompt's authoritative inventory line is DERIVED FROM the manifest and stays
    byte-identical to the legacy counting (single source of truth, no divergence),
  * the Markdown preservation block is generated from the same manifest,
  * the output assessment reconciles the base-render evidence against the SAME manifest
    (match proceeds; mismatch is NOT_VALIDATABLE, never a silent pass on the wrong set).
"""
from __future__ import annotations

from app.data import furniture_catalog
from app.services import furniture_manifest, prompt_service
from app.services import output_inventory_assessment_service as A


def _f(uid, item, cx, cy, w=100, h=100, rot=0):
    return {"uid": uid, "item_id": item, "cx": cx, "cy": cy, "w": w, "h": h, "rotation": rot}


def _legacy_counted(items):
    """The pre-refactor first-appearance counting, reproduced here so the test proves the
    manifest-derived line is byte-identical (not merely 'close')."""
    counts: dict[str, int] = {}
    order: list[str] = []
    for i in items:
        name = prompt_service._get_item_name(i)
        if name not in counts:
            order.append(name)
        counts[name] = counts.get(name, 0) + 1
    return ", ".join(f"{counts[n]}x {n}" for n in order)


# ── Stage D: the prompt consumes the manifest (single source, byte-identical) ──

def test_prompt_inventory_line_is_manifest_derived_and_byte_identical():
    cases = [
        # living area with a window placed as an item + a duplicate type
        [_f("so", "lounger-sofa", 500, 600, 1900, 900), _f("co", "console", 500, 180, 1100, 350),
         _f("wi", "window", 500, 850, 1800, 200)],
        # bedroom: bed + 2 identical side tables + window (duplicate counting + opening)
        [_f("b", "bed", 500, 350, 1800, 2000), _f("s1", "side-table", 300, 350),
         _f("s2", "side-table", 700, 350), _f("w", "window", 500, 800, 1500, 200)],
    ]
    for items in cases:
        enriched = [{**it, "_name": furniture_catalog.describe(it["item_id"])[0]} for it in items]
        via_manifest = prompt_service._counted_furniture(enriched)
        assert via_manifest == _legacy_counted(enriched)
        # and it genuinely comes through the manifest builder
        assert via_manifest == furniture_manifest.compact_inventory_line(
            furniture_manifest.build_room_manifest(enriched))


def test_build_room_prompts_lead_line_matches_manifest():
    canonical = {"furniture": [
        _f("b", "bed", 500, 350, 1800, 2000),
        _f("s1", "side-table", 300, 350), _f("s2", "side-table", 700, 350),
        _f("w", "window", 500, 800, 1500, 200),
    ]}
    _style, rooms = prompt_service.build_room_prompts(canonical, {"style": "Modern"})
    assert rooms, "expected at least one room prompt"
    label, prompt, _w, _h = rooms[0]
    m = furniture_manifest.room_manifest(canonical, label)
    line = furniture_manifest.compact_inventory_line(m)
    # the manifest inventory phrase appears verbatim in the room prompt
    assert line and line in prompt


# ── Stage E: output reconciled against the SAME manifest ───────────────────────

def _box(uid, item_id, x=100, y=100, w=160, h=90):
    return {"uid": uid, "item_id": item_id, "x": x, "y": y, "width": w, "height": h,
            "center_x": x + w / 2, "center_y": y + h / 2}


def _manifest_for_reconcile():
    canonical = {"furniture": [
        _f("b", "bed", 500, 350, 1800, 2000),
        _f("s1", "side-table", 300, 350), _f("s2", "side-table", 700, 350),
        _f("w", "window", 500, 800, 1500, 200),
    ]}
    return furniture_manifest.room_manifest(canonical, "Bedroom 1", design_version_id="v79")


def test_reconcile_match_by_uid_excludes_openings():
    m = _manifest_for_reconcile()
    # evidence carries the same 3 furniture uids (+ a window box, which must be ignored)
    boxes = [_box("b", "bed"), _box("s1", "side-table"), _box("s2", "side-table"),
             _box("w", "window")]
    r = A.reconcile_with_manifest(boxes, m)
    assert r["status"] == A.MATCH and r["basis"] == "uid" and r["furniture_count"] == 3


def test_reconcile_mismatch_when_evidence_missing_or_extra():
    m = _manifest_for_reconcile()
    missing_one = [_box("b", "bed"), _box("s1", "side-table")]  # s2 absent
    r1 = A.reconcile_with_manifest(missing_one, m)
    assert r1["status"] == A.MISMATCH and "s2" in r1["missing_uids"]

    extra_one = [_box("b", "bed"), _box("s1", "side-table"), _box("s2", "side-table"),
                 _box("x9", "floor-lamp")]
    r2 = A.reconcile_with_manifest(extra_one, m)
    assert r2["status"] == A.MISMATCH and "x9" in r2["extra_uids"]


def test_reconcile_falls_back_to_item_id_counts_without_uids():
    m = _manifest_for_reconcile()
    boxes = [{"item_id": "bed", "x": 0, "y": 0, "width": 10, "height": 10},
             {"item_id": "side-table", "x": 0, "y": 0, "width": 10, "height": 10},
             {"item_id": "side-table", "x": 0, "y": 0, "width": 10, "height": 10}]
    r = A.reconcile_with_manifest(boxes, m)
    assert r["status"] == A.MATCH and r["basis"] == "item_id_counts"


def test_reconcile_not_assessable_without_manifest_or_evidence():
    assert A.reconcile_with_manifest([_box("b", "bed")], None)["status"] == A.NOT_ASSESSABLE
    assert A.reconcile_with_manifest(None, _manifest_for_reconcile())["status"] == A.NOT_ASSESSABLE
    # evidence of only openings -> no furniture to reconcile
    assert A.reconcile_with_manifest([_box("w", "window")], _manifest_for_reconcile())["status"] == A.NOT_ASSESSABLE


# ── H1: duplicate stable ids are rejected, never a false match ─────────────────

def test_reconcile_duplicate_manifest_uid_is_ambiguous():
    # two placed items sharing a uid in the manifest -> identity ambiguous
    dup_manifest = furniture_manifest.build_room_manifest([
        _f("b", "bed", 500, 350, 1800, 2000),
        _f("s1", "side-table", 300, 350),
        _f("s1", "side-table", 700, 350),  # DUPLICATE uid
    ], room_label="Bedroom X")
    boxes = [_box("b", "bed"), _box("s1", "side-table"), _box("s2", "side-table")]
    r = A.reconcile_with_manifest(boxes, dup_manifest)
    assert r["status"] == A.AMBIGUOUS and r["duplicate_manifest_uid"] is True


def test_reconcile_duplicate_evidence_uid_is_ambiguous():
    m = _manifest_for_reconcile()
    boxes = [_box("b", "bed"), _box("s1", "side-table"), _box("s1", "side-table")]  # dup evidence uid
    r = A.reconcile_with_manifest(boxes, m)
    assert r["status"] == A.AMBIGUOUS and r["duplicate_evidence_uid"] is True


# ── H6: legitimately empty / openings-only rooms are defined, not silent ───────

def test_empty_room_has_no_manifest():
    assert furniture_manifest.room_manifest({"furniture": []}, "Bedroom 1") is None


def test_openings_only_room_has_zero_furniture_and_reconciles_not_assessable():
    canonical = {"furniture": [_f("w", "window", 500, 800, 1500, 200)]}
    # a window alone does not seed a room, so there is no furniture manifest for it
    m = furniture_manifest.room_manifest(canonical, "Interior")
    # Either no manifest, or a manifest whose expected furniture is empty -> NOT_ASSESSABLE
    exp = furniture_manifest.expected_inventory(m) if m else {"furniture_count": 0}
    assert exp["furniture_count"] == 0
    assert A.reconcile_with_manifest([_box("w", "window")], m)["status"] == A.NOT_ASSESSABLE
