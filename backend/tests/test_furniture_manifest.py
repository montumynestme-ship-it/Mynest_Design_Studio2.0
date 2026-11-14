"""Authoritative furniture manifest (spec §2) + empty-room hard gate (spec §4)."""

from unittest import mock

import pytest

from app.services import furniture_manifest, generation_service


def _f(uid, item, cx, cy, w=100, h=100, rot=0):
    return {"uid": uid, "item_id": item, "cx": cx, "cy": cy, "w": w, "h": h, "rotation": rot}


def _bedroom_canonical():
    return {
        "furniture": [
            _f("b", "bed", 500, 350, 1800, 2000),
            _f("s1", "side-table", 300, 350, 450, 450),
            _f("s2", "side-table", 700, 350, 450, 450),
            _f("w", "window", 500, 800, 1500, 200),
        ]
    }


def test_manifest_counts_furniture_excludes_openings():
    m = furniture_manifest.room_manifest(_bedroom_canonical(), "Bedroom 1")
    assert m is not None
    assert m["furniture_count"] == 3  # bed + 2 side tables; window excluded
    assert m["counts"]["Side Table"] == 2
    assert m["counts"]["Bed"] == 1
    assert m["window_count"] == 1


def test_manifest_records_full_transform_per_item():
    m = furniture_manifest.room_manifest(_bedroom_canonical(), "Bedroom 1")
    bed = next(i for i in m["items"] if i["item_id"] == "bed")
    for key in ("uid", "item_id", "name", "cx", "cy", "w", "h", "rotation"):
        assert key in bed
    assert bed["cx"] == 500 and bed["w"] == 1800 and bed["rotation"] == 0


def test_manifest_empty_for_room_without_furniture():
    assert furniture_manifest.room_manifest({"furniture": []}, "Bedroom 1") is None


def test_manifest_carries_version_binding_units_and_coordinate_system():
    m = furniture_manifest.room_manifest(
        _bedroom_canonical(), "Bedroom 1",
        design_version_id="v79", geometry_fingerprint="abc123",
    )
    assert m is not None
    assert m["schema_version"] == furniture_manifest.SCHEMA_VERSION
    assert m["design_version_id"] == "v79"
    assert m["geometry_fingerprint"] == "abc123"
    assert m["room_label"] == "Bedroom 1"
    assert m["units"] == furniture_manifest.UNITS
    assert m["coordinate_system"] == furniture_manifest.COORDINATE_SYSTEM
    assert isinstance(m["manifest_fingerprint"], str) and len(m["manifest_fingerprint"]) == 16


def test_binding_defaults_are_none_and_legacy_shape_preserved():
    """A caller that does not supply binding gets None (backward compatible) and the
    legacy keys still present."""
    m = furniture_manifest.room_manifest(_bedroom_canonical(), "Bedroom 1")
    assert m["design_version_id"] is None and m["geometry_fingerprint"] is None
    for key in ("furniture_count", "counts", "items", "door_count", "window_count"):
        assert key in m


def test_manifest_fingerprint_is_deterministic_for_same_snapshot():
    a = furniture_manifest.room_manifest(_bedroom_canonical(), "Bedroom 1", design_version_id="v79")
    b = furniture_manifest.room_manifest(_bedroom_canonical(), "Bedroom 1", design_version_id="v79")
    assert a["manifest_fingerprint"] == b["manifest_fingerprint"]
    # A different design version id yields a different fingerprint (it binds identity).
    c = furniture_manifest.room_manifest(_bedroom_canonical(), "Bedroom 1", design_version_id="v80")
    assert c["manifest_fingerprint"] != a["manifest_fingerprint"]


def test_compact_inventory_line_counts_all_items_including_openings():
    m = furniture_manifest.room_manifest(_bedroom_canonical(), "Bedroom 1")
    line = furniture_manifest.compact_inventory_line(m)
    assert "1x Bed" in line and "2x Side Table" in line and "1x Window" in line


def test_expected_inventory_excludes_openings_and_lists_uids():
    m = furniture_manifest.room_manifest(_bedroom_canonical(), "Bedroom 1")
    exp = furniture_manifest.expected_inventory(m)
    assert exp["furniture_count"] == 3
    assert exp["opening_count"] == 1
    assert exp["furniture_uids"] == ["b", "s1", "s2"]


def test_to_markdown_lists_real_items_and_rules_no_example_furniture():
    m = furniture_manifest.room_manifest(_bedroom_canonical(), "Bedroom 1", design_version_id="v79")
    md = furniture_manifest.to_markdown(m)
    assert "Bedroom 1" in md
    assert "Bed" in md and "Side Table" in md
    assert "Do NOT add, duplicate, substitute, merge, or invent" in md
    assert "v79" in md  # bound to the version
    # No illustrative/example furniture leaked in (only the design's real items).
    for bogus in ("Example Sofa", "placeholder", "sample "):
        assert bogus.lower() not in md.lower()


def test_every_canonical_item_appears_exactly_once_across_sections():
    """Inventory integrity (spec §2): sectioning drops no item and duplicates none —
    the union of section uids equals the canonical furniture uids, each exactly once;
    openings are excluded from the furniture manifest counts but still placed once."""
    from collections import Counter

    from app.services import prompt_service
    canonical = {"furniture": [
        _f("so", "lounger-sofa", 500, 600, 1900, 900),
        _f("co", "console", 500, 180, 1100, 350),
        _f("lw", "window", 500, 850, 1800, 200),
        _f("b1", "bed", 2500, 350, 1800, 2000),
        _f("s1", "side-table", 2300, 350, 450, 450),
        _f("s2", "side-table", 2700, 350, 450, 450),   # duplicate type, distinct uid
        _f("kb", "kitchen-base", 5000, 300, 2400, 600),
        _f("dt", "dining-table", 5000, 2500, 1500, 900),
    ]}
    groups = prompt_service.group_by_room(canonical["furniture"])
    placed = Counter(str(f.get("uid")) for _lbl, items in groups for f in items)
    expected = {str(f["uid"]) for f in canonical["furniture"]}
    assert set(placed) == expected                 # nothing dropped, nothing invented
    assert all(c == 1 for c in placed.values())     # nothing duplicated across sections
    # manifest furniture totals (openings excluded) sum to the non-opening count
    manifest = furniture_manifest.build_manifest(canonical)
    seen, total = set(), 0
    for lbl, m in manifest.items():
        if lbl in seen:
            continue
        seen.add(lbl); total += m["furniture_count"]
    assert total == 7                                # 8 items − 1 window opening


def test_gate_empty_room_never_calls_provider():
    """A room with no authoritative furniture must fail the gate before any provider call."""
    from app.services import floor_plan_service
    from app.services.ai.base import AIProviderAdapter, GenerationRequest

    class _WouldGenerate(AIProviderAdapter):
        name = "nvidia"
        model = "black-forest-labs/flux.1-dev"
        supports_control_image = True

        def __init__(self):
            self.called = False

        def generate(self, request: GenerationRequest):
            self.called = True
            return [b""]

    a = _WouldGenerate()
    with mock.patch("app.services.generation_service.AI_DEMO_MODE", False):
        with pytest.raises(floor_plan_service.FloorPlanError):
            generation_service._render_room(
                a, "nvidia", "Modern", ("Bedroom 1", "p", 1024, 768),
                ("proj", "fp", {"furniture": []}, None),
                generation_id="g", index=0, seed=1, fresh_generation=True,
                base_render=b"not-empty", scene_geometry_faithful=True,
            )
    assert a.called is False
