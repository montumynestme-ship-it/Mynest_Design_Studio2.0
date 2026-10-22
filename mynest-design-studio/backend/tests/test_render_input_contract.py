"""Phase 2I/2J regression tests for the render-input contract validator.

Covers: canonical UID coverage + unique room assignment, missing/extra/duplicate/
identity-mismatched furniture, unique/non-empty room ids + duplicate-room detection,
opening status validated against wall-verification evidence (missing/unknown never
silently PLACED; inconsistent status FAILs), render-attempt provenance (base sha/dims,
design-version correlation, actual-bytes match), and honest PASS/FAIL/UNCERTAIN
(incomplete evidence is never PASS; a fully evidenced valid input is PASS).
"""

from app.services.render_input_contract import validate_render_input, _is_opening


def _furn(uid, item_id="bed"):
    return {"uid": uid, "item_id": item_id, "cx": 1.0, "cy": 2.0, "w": 3.0, "h": 4.0, "rotation": 0.0}


def _scene(rooms, dvid="dv-1", fid="fp-1"):
    return {"floor_plan_id": fid, "design_version_id": dvid, "rooms": rooms}


def _clean_scene():
    rooms = [
        {"id": "bedroom-1", "label": "Bedroom 1",
         "furniture": [_furn("bed-1"), _furn("st-1", "side-table")],
         "opening_placements": [
             {"id": "door-1", "kind": "door", "source": "editor", "wall_id": "wall_1", "verified": True, "status": "PLACED"},
         ]},
        {"id": "kitchen", "label": "Kitchen",
         "furniture": [_furn("kb-1", "kitchen-base")],
         "opening_placements": []},
    ]
    canonical = {"furniture": [_furn("bed-1"), _furn("st-1", "side-table"), _furn("kb-1", "kitchen-base")]}
    return _scene(rooms), canonical


def test_is_opening_rule():
    assert _is_opening("door") and _is_opening("window") and _is_opening("bay-window-seat")
    assert not _is_opening("bed") and not _is_opening("side-table")


def test_clean_scene_passes():
    scene, canonical = _clean_scene()
    r = validate_render_input(scene, canonical)
    assert r["overall_status"] == "PASS"
    assert r["furniture"]["overall"] == "PASS"
    assert r["rooms"]["unique_ids"] is True
    assert r["provenance"] == "NOT_EVALUATED"  # no base/attempt metadata supplied


def test_missing_canonical_uid_fails():
    scene, canonical = _clean_scene()
    scene["rooms"][1]["furniture"] = []
    r = validate_render_input(scene, canonical)
    assert r["overall_status"] == "FAIL"
    assert "kb-1" in r["furniture"]["missing_uids"]


def test_unexpected_scene_uid_fails():
    scene, canonical = _clean_scene()
    scene["rooms"][0]["furniture"].append(_furn("ghost-1", "console"))
    r = validate_render_input(scene, canonical)
    assert r["overall_status"] == "FAIL"
    assert "ghost-1" in r["furniture"]["unexpected_uids"]


def test_duplicate_furniture_across_rooms_fails():
    scene, canonical = _clean_scene()
    scene["rooms"][1]["furniture"].append(_furn("bed-1"))
    r = validate_render_input(scene, canonical)
    assert r["overall_status"] == "FAIL"
    assert "bed-1" in r["furniture"]["duplicated_uids"]
    assert "bed-1" in r["rooms"]["overlapping_furniture_uids"]


def test_identity_mismatch_fails():
    # same uid but a DIFFERENT item_id in the scene than canonical -> identity mismatch
    scene, canonical = _clean_scene()
    scene["rooms"][0]["furniture"][0]["item_id"] = "wardrobe"  # bed-1 canonical is 'bed'
    r = validate_render_input(scene, canonical)
    assert r["overall_status"] == "FAIL"
    assert r["furniture"]["identity_mismatches"]
    assert r["furniture"]["identity_mismatches"][0]["uid"] == "bed-1"


def test_duplicate_room_ids_fails():
    scene, canonical = _clean_scene()
    scene["rooms"][1]["id"] = "bedroom-1"
    r = validate_render_input(scene, canonical)
    assert r["rooms"]["unique_ids"] is False
    assert r["overall_status"] == "FAIL"


def test_empty_room_id_fails():
    scene, canonical = _clean_scene()
    scene["rooms"][1]["id"] = "   "
    r = validate_render_input(scene, canonical)
    assert r["rooms"]["empty_id_indices"]
    assert r["overall_status"] == "FAIL"


def test_duplicate_room_labels_allowed_when_ids_unique():
    rooms = [
        {"id": "bedroom-3", "label": "Bedroom 3", "furniture": [_furn("b3")], "opening_placements": []},
        {"id": "bedroom-3-2", "label": "Bedroom 3", "furniture": [], "opening_placements": []},
    ]
    r = validate_render_input(_scene(rooms), {"furniture": [_furn("b3")]})
    assert "Bedroom 3" in r["rooms"]["duplicate_room_labels"]
    assert r["rooms"]["unique_ids"] is True
    assert r["overall_status"] == "PASS"


def test_opening_needs_review_is_uncertain():
    scene, canonical = _clean_scene()
    scene["rooms"][0]["opening_placements"].append(
        {"id": "win-x", "kind": "window", "source": "editor", "wall_id": None, "verified": False, "status": "NEEDS_REVIEW"}
    )
    r = validate_render_input(scene, canonical)
    assert r["openings"]["needs_review"] == 1 and r["openings"]["placed"] == 1
    assert r["overall_status"] == "UNCERTAIN"


def test_opening_unknown_status_never_placed():
    # Missing/unknown status must NOT silently become PLACED -> UNKNOWN -> UNCERTAIN.
    scene, canonical = _clean_scene()
    scene["rooms"][0]["opening_placements"] = [
        {"id": "d", "kind": "door", "wall_id": "w1", "verified": True},            # no status key
        {"id": "w", "kind": "window", "wall_id": "w2", "verified": True, "status": "WHATEVER"},  # invalid
    ]
    r = validate_render_input(scene, canonical)
    assert r["openings"]["placed"] == 0
    assert r["openings"]["unknown"] == 2
    assert r["overall_status"] == "UNCERTAIN"


def test_opening_status_inconsistent_fails():
    # Declared PLACED but no wall / not verified -> contradicts evidence -> INCONSISTENT -> FAIL.
    scene, canonical = _clean_scene()
    scene["rooms"][0]["opening_placements"] = [
        {"id": "d", "kind": "door", "wall_id": None, "verified": False, "status": "PLACED"},
    ]
    r = validate_render_input(scene, canonical)
    assert r["openings"]["inconsistent"] == 1
    assert r["overall_status"] == "FAIL"


def test_provenance_pass_requires_version_and_bytes_match():
    scene, canonical = _clean_scene()
    bm = {"sha256": "abc123", "width": 1216, "height": 832, "design_version_id": "dv-1"}
    r = validate_render_input(scene, canonical, base_meta=bm, base_image_sha256="abc123")
    assert r["provenance"] == "PASS"
    assert r["overall_status"] == "PASS"


def test_provenance_uncertain_without_byte_hash():
    # version matches but no actual base-bytes hash available -> cannot prove -> UNCERTAIN.
    scene, canonical = _clean_scene()
    bm = {"sha256": "abc123", "design_version_id": "dv-1"}
    r = validate_render_input(scene, canonical, base_meta=bm)
    assert r["provenance"] == "UNCERTAIN"
    assert r["overall_status"] == "UNCERTAIN"


def test_provenance_fail_on_version_mismatch():
    scene, canonical = _clean_scene()
    bm = {"sha256": "abc123", "design_version_id": "dv-OTHER"}
    r = validate_render_input(scene, canonical, base_meta=bm, base_image_sha256="abc123")
    assert r["provenance"] == "FAIL"
    assert r["overall_status"] == "FAIL"


def test_provenance_fail_on_stale_base_bytes():
    # metadata claims one sha; the ACTUAL hashed bytes differ -> stale/wrong file -> FAIL.
    scene, canonical = _clean_scene()
    bm = {"sha256": "abc123", "design_version_id": "dv-1"}
    r = validate_render_input(scene, canonical, base_meta=bm, base_image_sha256="DIFFERENT")
    assert r["provenance"] == "FAIL"
    assert r["overall_status"] == "FAIL"


def test_provenance_not_evaluated_without_metadata():
    scene, canonical = _clean_scene()
    r = validate_render_input(scene, canonical)
    assert r["provenance"] == "NOT_EVALUATED"
    assert r["base_correlation"] is None


def test_incomplete_evidence_never_silent_pass():
    r = validate_render_input(_scene([]), {"furniture": [_furn("bed-1")]})
    assert r["overall_status"] == "FAIL"
    assert "bed-1" in r["furniture"]["missing_uids"]
