"""Phase 4C Step 2K — detector-free inventory-mismatch status.

Locks the additive, surface-only inventory_status (MATCH / MISMATCH / NOT_ASSESSABLE)
that reports when a room's expected furniture manifest is not represented by the
deterministic base scene room actually selected for the render. Pure + offline:
no provider, no detector, no AI output, no DB.

The pinned regression structure mirrors design version 1831bf84 (independently
reproduced live during Step 2K): a CONFIRMED open-plan "Kitchen & Dining Area" holds
the dining table, while the section "Dining Area" resolves to an UNCERTAIN door-only
fallback twin — so the dining table is demonstrably absent from the base that render used.
"""

import json
from io import BytesIO
from types import SimpleNamespace
from unittest import mock

from PIL import Image

from app.services import base_inventory_service as B
from app.services import generation_service as G
from app.services.ai.base import AIProviderAdapter


# ── helpers ──────────────────────────────────────────────────────────────────

def _f(uid, item_id, name=None):
    return {"uid": uid, "item_id": item_id, "name": name or item_id}


def _manifest(items):
    # Mirror furniture_manifest.room_manifest shape: items carry uid/item_id/is_opening.
    _OPENING = {"window", "bay-window-seat", "door"}
    return {"items": [{**it, "is_opening": it["item_id"] in _OPENING} for it in items]}


def _room(rid, label, status, furniture):
    return {"id": rid, "label": label, "validation_status": status, "furniture": furniture}


def _solid_png(rgb, size=(96, 96)) -> bytes:
    b = BytesIO()
    Image.new("RGB", size, rgb).save(b, "PNG")
    return b.getvalue()


# ── 1. pinned Dining Area: reliable comparison, dining-table demonstrably absent ──

def test_pinned_dining_area_is_mismatch_with_grounded_reason():
    table = _f("dining-table-1787478800756", "dining-table", "Dining Table")
    combined = _room("kitchen-dining-area", "Kitchen & Dining Area", "CONFIRMED",
                     [table, _f("chimney-1", "chimney", "Chimney"),
                      _f("d-1", "door", "Door")])
    twin = _room("dining-area", "Dining Area", "UNCERTAIN", [_f("d-2", "door", "Door")])
    scene_rooms = [combined, twin]
    manifest = _manifest([table, _f("d-2", "door", "Door")])  # section expects the table

    status, reason = B.assess_section_base_inventory(manifest, twin, scene_rooms)
    assert status == "MISMATCH"
    assert reason["missing_uids"] == ["dining-table-1787478800756"]
    assert reason["missing_types"] == ["Dining Table"]
    assert reason["base_room_id"] == "dining-area"
    assert reason["base_room_status"] == "UNCERTAIN"


# ── 2. reliable matching room ──

def test_reliable_match_all_expected_present():
    bed = _f("bed-1", "bed", "Bed")
    wardrobe = _f("wardrobe-1", "wardrobe", "Wardrobe")
    room = _room("bedroom-1", "Bedroom 1", "CONFIRMED", [bed, wardrobe, _f("d-1", "door")])
    manifest = _manifest([bed, wardrobe, _f("d-1", "door")])
    status, reason = B.assess_section_base_inventory(manifest, room, [room])
    assert status == "MATCH"
    assert reason["base_room_status"] == "CONFIRMED"


# ── 3. NOT_ASSESSABLE / nullable paths ──

def test_no_base_room_is_not_assessable():
    manifest = _manifest([_f("bed-1", "bed", "Bed")])
    status, reason = B.assess_section_base_inventory(manifest, None, [])
    assert status == "NOT_ASSESSABLE"
    assert "no deterministic base scene room" in reason["reason"]


def test_no_expected_inventory_is_not_assessable():
    room = _room("r", "R", "CONFIRMED", [_f("bed-1", "bed")])
    assert B.assess_section_base_inventory(None, room, [room])[0] == "NOT_ASSESSABLE"
    # openings-only manifest -> nothing to assess
    openings_only = _manifest([_f("d-1", "door"), _f("w-1", "window")])
    assert B.assess_section_base_inventory(openings_only, room, [room])[0] == "NOT_ASSESSABLE"


def test_missing_item_not_locatable_anywhere_is_not_assessable():
    # Expected item absent from the base AND from every scene room -> uncertain, never MISMATCH.
    bed = _f("bed-1", "bed", "Bed")
    ghost = _f("ghost-1", "sofa", "Sofa")  # never appears in the scene
    base = _room("r", "R", "UNCERTAIN", [bed])
    manifest = _manifest([bed, ghost])
    status, reason = B.assess_section_base_inventory(manifest, base, [base])
    assert status == "NOT_ASSESSABLE"
    assert "not locatable" in reason["reason"]


# ── 4. uncertain membership never yields a false definitive ──

def test_uncertain_membership_no_false_mismatch_or_match():
    # An UNCERTAIN base missing an item that is NOT elsewhere -> NOT_ASSESSABLE (not MISMATCH).
    a = _f("a", "bed", "Bed")
    missing = _f("b", "sofa", "Sofa")
    base = _room("fallback", "Fallback", "UNCERTAIN", [a])
    status, _ = B.assess_section_base_inventory(_manifest([a, missing]), base, [base])
    assert status == "NOT_ASSESSABLE"
    # But a genuine, locatable omission from an UNCERTAIN base IS a real mismatch (pinned case).
    other = _room("other", "Other", "CONFIRMED", [missing])
    status2, _ = B.assess_section_base_inventory(_manifest([a, missing]), base, [base, other])
    assert status2 == "MISMATCH"


# ── 5. openings are kept separate from the furniture comparison ──

def test_openings_excluded_from_furniture_comparison():
    bed = _f("bed-1", "bed", "Bed")
    # Expected has a door the base lacks; doors are NOT furniture -> still MATCH on furniture.
    base = _room("r", "R", "CONFIRMED", [bed])
    manifest = _manifest([bed, _f("d-1", "door", "Door")])
    assert B.assess_section_base_inventory(manifest, base, [base])[0] == "MATCH"


# ── 6/7/8. persistence + serialization + legacy compatibility ──

def test_save_debug_artifacts_persists_inventory(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "DEBUG_ARTIFACTS_DIR", tmp_path)
    G._save_debug_artifacts(
        "g1", 0, "Dining Area", "p", "fal", "m", 1216, 832, "success",
        geometry_status="UNVERIFIED", postgen_status="OK",
        inventory_status="MISMATCH",
        inventory_reason={"missing_types": ["Dining Table"], "base_room_id": "dining-area"},
    )
    rd = json.loads((tmp_path / "g1" / "room_0_Dining Area" / "render_debug.json").read_text("utf-8"))
    assert rd["inventory_status"] == "MISMATCH"
    assert rd["inventory_reason"]["missing_types"] == ["Dining Table"]
    # independence — the inventory signal does not touch geometry/postgen fields.
    assert rd["geometry_status"] == "UNVERIFIED"
    assert rd["postgen_status"] == "OK"


def _resp(dbg):
    gen = SimpleNamespace(id="g1")
    img = SimpleNamespace(id="img1", image_url="/x", label="Dining Area",
                          design_index=1, total_designs=1)
    return G._image_response(gen, img, {}, lambda _l: None, lambda _l: None, lambda *_a: dbg)


def test_image_response_surfaces_inventory_status():
    r = _resp({"inventory_status": "MISMATCH",
               "inventory_reason": {"missing_types": ["Dining Table"]},
               "geometry_status": "UNVERIFIED", "postgen_status": "OK"})
    assert r.inventory_status == "MISMATCH"
    assert r.inventory_reason["missing_types"] == ["Dining Table"]
    # independence preserved through serialization
    assert r.geometry_status == "UNVERIFIED"
    assert r.postgen_status == "OK"


def test_image_response_missing_inventory_is_none_backward_compatible():
    # Legacy render_debug.json without the new fields -> None, never a crash.
    r = _resp({"geometry_status": "UNVERIFIED"})
    assert r.inventory_status is None
    assert r.inventory_reason is None


# ── Correction 1 — uid-less expected furniture never yields a silent MATCH ──

def test_uidless_expected_furniture_is_not_assessable():
    bed = _f("bed-1", "bed", "Bed")
    lamp_no_uid = {"item_id": "lamp", "name": "Lamp"}  # furniture, no stable uid
    base = _room("r", "R", "CONFIRMED", [bed])         # base has bed; lamp genuinely absent
    man = {"items": [{**bed, "is_opening": False}, {**lamp_no_uid, "is_opening": False}]}
    status, reason = B.assess_section_base_inventory(man, base, [base])
    assert status == "NOT_ASSESSABLE"
    assert "lacks a stable uid" in reason["reason"]


# ── Correction 3 — cache-hit base provenance gate (unit) ──

def test_inventory_status_for_cache_hit_matching_provenance_preserves(monkeypatch):
    monkeypatch.setattr(G, "_read_cache_provenance",
                        lambda _k: {"base_sha256": "abc", "base_room_id": "dining-area"})
    status, reason = G._inventory_status_for_cache_hit(
        "ck", "abc", "dining-area", "MISMATCH", {"missing_uids": ["t"]})
    assert status == "MISMATCH" and reason == {"missing_uids": ["t"]}


def test_inventory_status_for_cache_hit_missing_sidecar_is_not_assessable(monkeypatch):
    monkeypatch.setattr(G, "_read_cache_provenance", lambda _k: None)  # legacy entry
    status, reason = G._inventory_status_for_cache_hit("ck", "abc", "dining-area", "MISMATCH", {})
    assert status == "NOT_ASSESSABLE" and reason["provenance"] == "unverified"


def test_inventory_status_for_cache_hit_differing_provenance_is_not_assessable(monkeypatch):
    monkeypatch.setattr(G, "_read_cache_provenance",
                        lambda _k: {"base_sha256": "DIFFERENT", "base_room_id": "dining-area"})
    assert G._inventory_status_for_cache_hit("ck", "abc", "dining-area", "MISMATCH", {})[0] == "NOT_ASSESSABLE"


def test_inventory_status_for_cache_hit_differing_room_is_not_assessable(monkeypatch):
    # Matching hash but different resolved room -> NOT_ASSESSABLE (hash alone is not claimed
    # to prove room association).
    monkeypatch.setattr(G, "_read_cache_provenance",
                        lambda _k: {"base_sha256": "abc", "base_room_id": "OTHER"})
    assert G._inventory_status_for_cache_hit("ck", "abc", "dining-area", "MATCH", {})[0] == "NOT_ASSESSABLE"


def test_inventory_status_for_cache_hit_unknown_current_base_is_not_assessable(monkeypatch):
    monkeypatch.setattr(G, "_read_cache_provenance",
                        lambda _k: {"base_sha256": "abc", "base_room_id": "dining-area"})
    # current base sha is None (e.g. no base) -> cannot prove match
    assert G._inventory_status_for_cache_hit("ck", None, "dining-area", "MISMATCH", {})[0] == "NOT_ASSESSABLE"


def test_cache_provenance_sidecar_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "RENDER_CACHE_DIR", tmp_path)
    G._write_cache_provenance("ckey", "sha-123", "dining-area")
    assert G._read_cache_provenance("ckey") == {"base_sha256": "sha-123", "base_room_id": "dining-area"}
    # No base -> no sidecar written (text-to-image path).
    G._write_cache_provenance("ckey2", None, None)
    assert G._read_cache_provenance("ckey2") is None


# ── Correction 3 — cache-hit through _render_room, provenance-gated end to end ──

class _CtrlAdapter(AIProviderAdapter):
    name = "fal"
    model = "m"
    supports_control_image = True

    def generate(self, request):  # unreached on a cache hit
        return [_solid_png((9, 9, 9))]


def _run_cache_hit(tmp_path, monkeypatch, provenance):
    """Drive _render_room down the cache-hit path with a given recorded provenance
    (None = legacy / no sidecar). Returns the persisted render_debug.json."""
    monkeypatch.setattr(G, "DEBUG_ARTIFACTS_DIR", tmp_path)
    monkeypatch.setattr(G, "_get_cached_render", lambda _k: _solid_png((230, 230, 230)))
    monkeypatch.setattr(G, "_classify_base_gate", lambda *_a, **_k: ("", ""))  # gate passes
    monkeypatch.setattr(G, "_read_cache_provenance", lambda _k: provenance)
    table = _f("dining-table-1", "dining-table", "Dining Table")
    combined = _room("kitchen-dining-area", "Kitchen & Dining Area", "CONFIRMED", [table])
    twin = _room("dining-area", "Dining Area", "UNCERTAIN", [_f("d-2", "door", "Door")])
    canonical = {"furniture": [
        {"uid": "dining-table-1", "item_id": "dining-table", "cx": 320, "cy": 120, "w": 120, "h": 80, "rotation": 0},
        {"uid": "d-2", "item_id": "door", "cx": 400, "cy": 40, "w": 40, "h": 10, "rotation": 0},
    ]}
    base_render = _solid_png((120, 120, 120))
    with mock.patch.object(G, "AI_DEMO_MODE", False):
        res = G._render_room(
            _CtrlAdapter(), "fal", "Modern", ("Dining Area", "p", 1024, 768),
            ("proj", "fp", canonical, None), generation_id="gInv", index=0, seed=1,
            fresh_generation=False, base_render=base_render,
            scene_geometry_faithful=True, base_scene_room=twin, scene_rooms=[combined, twin],
        )
    assert res[5] is True  # cache_hit
    import hashlib as _h
    sha = _h.sha256(base_render).hexdigest()
    rd = json.loads((tmp_path / "gInv" / "room_0_Dining Area" / "render_debug.json").read_text("utf-8"))
    return rd, sha


def test_cache_hit_matching_provenance_preserves_mismatch(tmp_path, monkeypatch):
    # Record provenance that matches THIS request's base (same sha + resolved room).
    base_render = _solid_png((120, 120, 120))
    import hashlib as _h
    sha = _h.sha256(base_render).hexdigest()
    rd, _ = _run_cache_hit(tmp_path, monkeypatch, {"base_sha256": sha, "base_room_id": "dining-area"})
    assert rd["inventory_status"] == "MISMATCH"
    assert "dining-table-1" in rd["inventory_reason"]["missing_uids"]


def test_cache_hit_legacy_no_provenance_is_not_assessable(tmp_path, monkeypatch):
    rd, _ = _run_cache_hit(tmp_path, monkeypatch, None)      # legacy entry, no sidecar
    assert rd["inventory_status"] == "NOT_ASSESSABLE"
    assert rd["inventory_reason"]["provenance"] == "unverified"


def test_cache_hit_differing_provenance_is_not_assessable(tmp_path, monkeypatch):
    rd, _ = _run_cache_hit(tmp_path, monkeypatch, {"base_sha256": "OTHER", "base_room_id": "dining-area"})
    assert rd["inventory_status"] == "NOT_ASSESSABLE"


def test_cache_hit_malformed_sidecar_is_not_assessable(tmp_path, monkeypatch):
    # A sidecar missing the expected keys must not be treated as a provenance match.
    rd, _ = _run_cache_hit(tmp_path, monkeypatch, {"unexpected": "shape"})
    assert rd["inventory_status"] == "NOT_ASSESSABLE"


def test_read_cache_provenance_handles_corrupt_json(tmp_path, monkeypatch):
    # Corrupt/partial JSON on disk -> None (never raises), so the caller falls back to
    # NOT_ASSESSABLE rather than crashing or trusting garbage.
    monkeypatch.setattr(G, "RENDER_CACHE_DIR", tmp_path)
    G._cache_provenance_path("ck").write_text("{ not json", encoding="utf-8")
    assert G._read_cache_provenance("ck") is None


# ── Phase D — duplicate room labels resolve to the first-emitted (base's) room ──

def test_resolve_base_scene_room_duplicate_label_picks_first_emitted():
    # Two rooms share the label "Bedroom 3" (CONFIRMED first, UNCERTAIN fallback twin),
    # mirroring 1831bf84. The frontend keys the label to the FIRST valid capture, so the
    # resolver must return that same first room — not the twin — for the base key.
    confirmed = _room("bedroom-3", "Bedroom 3", "CONFIRMED", [_f("bed-3", "bed")])
    twin = _room("bedroom-3-2", "Bedroom 3", "UNCERTAIN", [_f("win-3", "window")])
    rooms = [confirmed, twin]
    # matched key is the display label (as the frontend emits it)
    assert G._resolve_base_scene_room(rooms, "Bedroom 3")["id"] == "bedroom-3"
    # a stable id key resolves unambiguously to its own room (twin by id)
    assert G._resolve_base_scene_room(rooms, "bedroom-3-2")["id"] == "bedroom-3-2"
    # unknown / empty -> None (caller yields NOT_ASSESSABLE)
    assert G._resolve_base_scene_room(rooms, None) is None
    assert G._resolve_base_scene_room([], "Bedroom 3") is None


# ── Phase F — a FAILED generation must not leave misleading provenance ──

def test_failed_generation_writes_no_cache_provenance(tmp_path, monkeypatch):
    # Provenance is written only on the fresh-SUCCESS path (after _save_cached_render).
    # A provider failure must not persist a sidecar that a later hit could trust.
    monkeypatch.setattr(G, "DEBUG_ARTIFACTS_DIR", tmp_path)
    monkeypatch.setattr(G, "RENDER_CACHE_DIR", tmp_path)
    monkeypatch.setattr(G, "_classify_base_gate", lambda *_a, **_k: ("", ""))

    class _FailAdapter(AIProviderAdapter):
        name = "fal"; model = "m"; supports_control_image = True
        def generate(self, request):
            raise RuntimeError("provider boom")

    canonical = {"furniture": [
        {"uid": "dining-table-1", "item_id": "dining-table", "cx": 320, "cy": 120, "w": 120, "h": 80, "rotation": 0},
    ]}
    twin = _room("dining-area", "Dining Area", "UNCERTAIN", [_f("d-2", "door", "Door")])
    import pytest
    with mock.patch.object(G, "AI_DEMO_MODE", False), pytest.raises(Exception):
        G._render_room(
            _FailAdapter(), "fal", "Modern", ("Dining Area", "p", 1024, 768),
            ("proj", "fp", canonical, None), generation_id="gFail", index=0, seed=1,
            fresh_generation=True, base_render=_solid_png((120, 120, 120)),
            scene_geometry_faithful=True, base_scene_room=twin, scene_rooms=[twin],
        )
    # no provenance sidecar was written for this failed room
    assert list(tmp_path.glob("*.base.json")) == []
