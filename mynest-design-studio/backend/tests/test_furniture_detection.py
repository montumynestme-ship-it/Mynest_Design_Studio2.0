"""Furniture/fixture detection CANDIDATE layer (audit stage 6, reinforced).

Feeds synthetic raw detections into the deterministic candidate builder (no model
required) and checks: classification→item_id, duplicate dedup, overlapping
detections (no silent merge), rotated furniture, multiple identical objects,
confidence thresholds, and the source-of-truth invariants (candidate ≠ canonical,
coordinates preserved/not moved, nothing fabricated).
"""

from app.data.classes import ml_class_to_item_id
from app.services import furniture_detection_service as fd


def _det(cls, bbox, conf=0.9, rot=0.0, did=None):
    return {"id": did, "class_name": cls, "bbox": bbox, "confidence": conf, "rotation": rot}


# ── Classification ───────────────────────────────────────────────────────────

def test_classification_maps_target_classes_to_item_ids():
    classes = ["bed", "side_table", "dressing", "loungers_sofa", "center_table",
               "dining_table", "dining_chair", "kitchen_base", "chimney", "console",
               "partition", "wardrobe", "shoe_rack", "door", "window"]
    raw = [_det(c, [i * 60, 0, i * 60 + 40, 40]) for i, c in enumerate(classes)]
    res = fd.build_candidates(raw, min_confidence=0.1)
    by_class = {c["class_name"]: c for c in res["candidates"]}
    assert len(by_class) == len(classes)
    for c in classes:
        assert by_class[c]["item_id"] == ml_class_to_item_id(c)
    assert by_class["loungers_sofa"]["item_id"] == "lounger-sofa"
    assert by_class["dining_chair"]["item_id"] == "dining-chair"


# ── Duplicate detections ─────────────────────────────────────────────────────

def test_duplicate_detections_deduped_keep_highest_confidence():
    raw = [_det("bed", [0, 0, 100, 100], conf=0.60, did="a"),
           _det("bed", [2, 2, 102, 102], conf=0.90, did="b")]   # ~0.92 IoU, same class
    res = fd.build_candidates(raw)
    beds = [c for c in res["candidates"] if c["class_name"] == "bed"]
    assert len(beds) == 1
    assert beds[0]["confidence"] == 0.90
    assert beds[0]["id"] == "b"


# ── Overlapping detections (different class → never merged) ───────────────────

def test_overlapping_different_class_kept_and_marked_uncertain():
    raw = [_det("bed", [0, 0, 100, 100], conf=0.9, did="bed"),
           _det("wardrobe", [10, 10, 110, 110], conf=0.8, did="wr")]   # IoU ~0.68
    res = fd.build_candidates(raw)
    assert res["stats"]["total"] == 2                     # both kept — NOT merged
    ids = {c["id"]: c for c in res["candidates"]}
    assert ids["bed"]["status"] == "UNCERTAIN"
    assert ids["wr"]["status"] == "UNCERTAIN"
    assert "wr" in ids["bed"]["overlaps"] and "bed" in ids["wr"]["overlaps"]


# ── Rotated furniture ────────────────────────────────────────────────────────

def test_rotated_furniture_rotation_preserved():
    res = fd.build_candidates([_det("bed", [0, 0, 100, 200], conf=0.9, rot=90.0)])
    assert res["candidates"][0]["rotation"] == 90.0


# ── Multiple identical objects ───────────────────────────────────────────────

def test_multiple_identical_objects_all_kept():
    raw = [_det("side_table", [0, 0, 50, 50], conf=0.8, did="s1"),
           _det("side_table", [400, 400, 450, 450], conf=0.8, did="s2")]  # distinct
    res = fd.build_candidates(raw)
    tables = [c for c in res["candidates"] if c["class_name"] == "side_table"]
    assert len(tables) == 2
    assert {t["id"] for t in tables} == {"s1", "s2"}


# ── Confidence thresholds ────────────────────────────────────────────────────

def test_confidence_thresholds_uncertain_and_drop():
    raw = [_det("bed", [0, 0, 100, 100], conf=0.90, did="hi"),
           _det("sofa" if False else "console", [300, 0, 360, 40], conf=0.15, did="lo"),
           _det("chimney", [600, 0, 640, 40], conf=0.02, did="noise")]
    res = fd.build_candidates(raw, min_confidence=0.25, drop_below=0.05)
    ids = {c["id"]: c for c in res["candidates"]}
    assert "noise" not in ids                       # dropped below hard floor
    assert ids["hi"]["status"] == "CANDIDATE"
    assert ids["lo"]["status"] == "UNCERTAIN"        # kept but low-confidence
    assert ids["lo"]["confidence"] == 0.15           # preserved verbatim


def test_min_confidence_does_not_delete_only_flags():
    raw = [_det("bed", [0, 0, 100, 100], conf=0.30)]
    res = fd.build_candidates(raw, min_confidence=0.5)
    assert res["stats"]["total"] == 1
    assert res["candidates"][0]["status"] == "UNCERTAIN"


# ── Source-of-truth invariants ───────────────────────────────────────────────

def test_candidates_are_not_canonical_truth():
    res = fd.build_candidates([_det("bed", [0, 0, 100, 100])])
    assert res["note"] == "candidates are proposals, NOT canonical truth"
    assert all(c["status"] in ("CANDIDATE", "UNCERTAIN") for c in res["candidates"])


def test_coordinates_preserved_not_moved():
    res = fd.build_candidates([_det("bed", [30, 40, 130, 240])])
    c = res["candidates"][0]
    assert c["bbox"] == [30.0, 40.0, 130.0, 240.0]     # verbatim, not moved
    assert c["cx"] == 80.0 and c["cy"] == 140.0        # centre derived
    assert c["w"] == 100.0 and c["h"] == 200.0


def test_center_wh_input_form_supported():
    raw = [{"class_name": "console", "cx": 100, "cy": 50, "w": 60, "h": 20, "confidence": 0.8}]
    c = fd.build_candidates(raw)["candidates"][0]
    assert c["bbox"] == [70.0, 40.0, 130.0, 60.0]

def test_empty_input_no_fabrication():
    res = fd.build_candidates([])
    assert res["candidates"] == [] and res["stats"]["total"] == 0


def test_normalized_bbox_only_with_image_size():
    raw = [_det("bed", [100, 50, 300, 250])]
    assert "bbox_normalized" not in fd.build_candidates(raw)["candidates"][0]
    c = fd.build_candidates(raw, image_size=(1000, 500))["candidates"][0]
    assert c["bbox_normalized"] == [0.1, 0.1, 0.3, 0.5]
