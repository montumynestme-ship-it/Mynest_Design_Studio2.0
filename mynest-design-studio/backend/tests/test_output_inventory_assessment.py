"""Phase 1 — advisory output-inventory assessment (offline; stub detector; no OWLv2/paid).

Covers the evidence contract (version-bound, malformed/duplicate/mismatch rejection),
the advisory assessment (missing/extra via a stub detector; detector/image/evidence
unavailable → NOT_VALIDATABLE, never PASS/FAITHFUL), backward compatibility (no evidence),
and the request-schema optionality. No weights downloaded, no generation, no DB writes.
"""
from __future__ import annotations

from app.services import output_inventory_assessment_service as A
from app.schemas.generation import GenerationRequestBody


def _box(uid, item_id, x, y, w=160, h=90, room="Living Area"):
    return {"uid": uid, "item_id": item_id, "x": x, "y": y, "width": w, "height": h,
            "center_x": x + w / 2, "center_y": y + h / 2, "room": room}


def _det(x, y, w=160, h=90, query="sofa", score=0.9):
    return {"x": x, "y": y, "width": w, "height": h, "query": query, "score": score}


BOXES = [_box("sofa-1", "lounger-sofa", 200, 500), _box("console-1", "console", 800, 520, 150, 60)]


# ── evidence validation ───────────────────────────────────────────────────────

def test_version_mismatch_rejected():
    clean, why = A.validate_base_box_evidence(BOXES, expected_version_id="v79", declared_version_id="v80")
    assert clean is None and why == "VERSION_MISMATCH"


def test_same_version_accepted():
    clean, why = A.validate_base_box_evidence(BOXES, expected_version_id="v79", declared_version_id="v79")
    assert why is None and len(clean) == 2


def test_malformed_and_nonpositive_and_duplicate_rejected():
    assert A.validate_base_box_evidence([{"uid": "a", "item_id": "x"}])[1] == "MALFORMED_BOX"
    assert A.validate_base_box_evidence([_box("a", "x", 0, 0, 0, 10)])[1] == "NON_POSITIVE_BOX"
    assert A.validate_base_box_evidence([_box("dup", "x", 0, 0), _box("dup", "y", 9, 9)])[1] == "DUPLICATE_UID"
    assert A.validate_base_box_evidence([])[1] == "NO_BOXES"


# ── advisory assessment: unavailable paths never pass ─────────────────────────

def test_no_evidence_image_or_detector_is_not_validatable():
    assert A.assess_output_inventory(None, object(), detector=lambda i: [])["overall_status"] == "NOT_VALIDATABLE"
    assert A.assess_output_inventory(BOXES, None, detector=lambda i: [])["overall_status"] == "NOT_VALIDATABLE"
    r = A.assess_output_inventory(BOXES, object(), detector=None)
    assert r["overall_status"] == "NOT_VALIDATABLE" and r["advisory"] is True
    assert "no output detector" in r["reason"]


def test_detector_exception_is_not_validatable_never_pass():
    def boom(_img):
        raise RuntimeError("owlv2 weights not installed")
    r = A.assess_output_inventory(BOXES, object(), detector=boom)
    assert r["overall_status"] == "NOT_VALIDATABLE" and "detector unavailable" in r["reason"]


# ── advisory assessment: missing / extra candidates (stub detector) ───────────

def test_missing_candidate_flagged_advisory():
    # only the console detected; the sofa is a MISSING candidate
    r = A.assess_output_inventory(BOXES, object(), detector=lambda i: [_det(800, 520, 150, 60, "console")])
    assert r["advisory"] is True
    assert r["missing_count"] >= 1 and r["overall_status"] != "PASS"


def test_extra_candidate_flagged_advisory():
    r = A.assess_output_inventory(
        BOXES, object(),
        detector=lambda i: [_det(200, 500, query="sofa"), _det(800, 520, 150, 60, "console"),
                            _det(1100, 120, 120, 120, "floor lamp", 0.95)])
    assert r["advisory"] is True
    assert r["extra_candidate_count"] >= 1 and r["overall_status"] != "PASS"


# ── output-vs-capture dimension correspondence (Phase 2) ──────────────────────

def test_output_dims_mismatch_is_not_validatable():
    # detector would run, but output dims differ from the capture frame -> correspondence
    # is not established -> NOT_VALIDATABLE (no silent scaling).
    r = A.assess_output_inventory(
        BOXES, object(), detector=lambda i: [_det(200, 500, query="sofa")],
        image_width=1216, image_height=832, output_width=1344, output_height=768)
    assert r["overall_status"] == "NOT_VALIDATABLE" and "differ from the base capture" in r["reason"]


def test_output_dims_match_proceeds_to_assessment():
    r = A.assess_output_inventory(
        BOXES, object(),
        detector=lambda i: [_det(200, 500, query="sofa"), _det(800, 520, 150, 60, "console")],
        image_width=1216, image_height=832, output_width=1216, output_height=832)
    assert r.get("advisory") is True and r["overall_status"] != "NOT_VALIDATABLE"


# ── request schema: optional + backward compatible ───────────────────────────

def test_request_base_boxes_optional_and_default_none():
    assert "base_boxes" in GenerationRequestBody.model_fields
    assert GenerationRequestBody().base_boxes is None                      # backward compatible
    body = GenerationRequestBody(base_boxes={"Living Area": BOXES})
    assert body.base_boxes["Living Area"][0]["uid"] == "sofa-1"


# ── Phase 2 regression tests ──────────────────────────────────────────────────

def test_nan_and_infinite_coordinates_rejected():
    nan_box = _box("nan-1", "sofa", 200, 500, float("nan"), 90)
    inf_box = _box("inf-1", "sofa", float("inf"), 500, 160, 90)
    assert A.validate_base_box_evidence([nan_box])[1] == "MALFORMED_BOX"
    assert A.validate_base_box_evidence([inf_box])[1] == "MALFORMED_BOX"


def test_invalid_base_image_dimensions_rejected():
    r1 = A.assess_output_inventory(BOXES, object(), detector=lambda i: [], image_width=0, image_height=832)
    assert r1["overall_status"] == "NOT_VALIDATABLE" and "must be positive" in r1["reason"]
    r2 = A.assess_output_inventory(BOXES, object(), detector=lambda i: [], image_width=-100, image_height=-100)
    assert r2["overall_status"] == "NOT_VALIDATABLE" and "must be positive" in r2["reason"]


def test_output_dimensions_auto_detected_from_pil_image():
    from PIL import Image
    mismatched_img = Image.new("RGB", (1024, 768))
    r = A.assess_output_inventory(
        BOXES, mismatched_img, detector=lambda i: [_det(200, 500, query="sofa")],
        image_width=1216, image_height=832)
    assert r["overall_status"] == "NOT_VALIDATABLE"
    assert "differ from the base capture frame" in r["reason"]
    assert "1024x768" in r["reason"]


def test_calibration_status_always_not_calibrated():
    # Unavailable path
    r_unavail = A.assess_output_inventory(None, object(), detector=None)
    assert r_unavail["calibration_status"] == "NOT_CALIBRATED"

    # Evaluated path
    r_eval = A.assess_output_inventory(
        BOXES, object(),
        detector=lambda i: [_det(200, 500, query="sofa"), _det(800, 520, 150, 60, "console")],
        image_width=1216, image_height=832, output_width=1216, output_height=832)
    assert r_eval["calibration_status"] == "NOT_CALIBRATED"
    assert r_eval["advisory"] is True


def test_duplicate_and_ambiguous_detections_flagged_extra_never_faithful():
    # Multiple detections of the same category (duplicate sofa detections)
    # One sofa matches the base; the other is classified as extra candidate
    dets = [
        _det(200, 500, 160, 90, "sofa", score=0.92),
        _det(205, 505, 160, 90, "sofa", score=0.88),  # duplicate detection of same object
        _det(800, 520, 150, 60, "console", score=0.89),
    ]
    r = A.assess_output_inventory(
        BOXES, object(), detector=lambda i: dets,
        image_width=1216, image_height=832, output_width=1216, output_height=832)
    assert r["advisory"] is True
    # The duplicate detection is routed to extras
    assert r["extra_candidate_count"] >= 1
    # Duplicate/extra candidate prevents a clean PASS -> downgrades to UNCERTAIN
    assert r["overall_status"] == "UNCERTAIN"


# ── version binding: missing declared version is rejected (H5) ────────────────

def test_missing_declared_version_rejected_when_expected_present():
    clean, why = A.validate_base_box_evidence(BOXES, expected_version_id="v79", declared_version_id=None)
    assert clean is None and why == "MISSING_DECLARED_VERSION"


def test_no_expected_version_skips_binding_backward_compatible():
    # legacy/non-production callers that assert no expected version are unaffected
    clean, why = A.validate_base_box_evidence(BOXES)
    assert why is None and len(clean) == 2
    clean2, why2 = A.validate_base_box_evidence(BOXES, declared_version_id="whatever")
    assert why2 is None and len(clean2) == 2


# ── malformed evidence cannot enter assessment via any caller (H4) ────────────

def test_assess_rejects_malformed_evidence_internally():
    malformed = [{"uid": "a", "item_id": "x"}]  # missing x/y/width/height
    r = A.assess_output_inventory(malformed, object(), detector=lambda i: [])
    assert r["overall_status"] == "NOT_VALIDATABLE" and "malformed base furniture evidence" in r["reason"]

    dup = [_box("d", "sofa", 0, 0), _box("d", "console", 9, 9)]  # duplicate uid
    r2 = A.assess_output_inventory(dup, object(), detector=lambda i: [])
    assert r2["overall_status"] == "NOT_VALIDATABLE" and "DUPLICATE_UID" in r2["reason"]


# ── openings excluded from furniture matching (H3) ────────────────────────────

def test_opening_boxes_not_matched_as_furniture():
    # a window box in the base evidence must not become a furniture object (and so must
    # not be reported missing/extra); only the sofa is a furniture object here.
    boxes = [_box("sofa-1", "lounger-sofa", 200, 500), _box("win-1", "window", 900, 100, 300, 80)]
    r = A.assess_output_inventory(
        boxes, object(), detector=lambda i: [_det(200, 500, query="sofa")],
        image_width=1216, image_height=832, output_width=1216, output_height=832)
    item_ids = {o["item_id"] for o in r["objects"]}
    assert item_ids == {"lounger-sofa"}          # window excluded from furniture objects
    assert r["missing_count"] == 0                # the sofa matched; window not counted missing


def test_only_openings_evidence_is_not_validatable():
    boxes = [_box("win-1", "window", 900, 100, 300, 80)]
    r = A.assess_output_inventory(
        boxes, object(), detector=lambda i: [_det(900, 100, 300, 80, "window")],
        image_width=1216, image_height=832, output_width=1216, output_height=832)
    assert r["overall_status"] == "NOT_VALIDATABLE" and "openings only" in r["reason"]


# ── equal dimensions do not establish camera comparability (H2) ───────────────

def test_equal_dims_flags_camera_comparability_unverified():
    r = A.assess_output_inventory(
        BOXES, object(),
        detector=lambda i: [_det(200, 500, query="sofa"), _det(800, 520, 150, 60, "console")],
        image_width=1216, image_height=832, output_width=1216, output_height=832)
    assert r["camera_comparability"] == "UNVERIFIED"
    assert r["advisory"] is True


def test_base_boxes_not_mutated_by_assessment():
    import copy
    orig_boxes = copy.deepcopy(BOXES)
    A.assess_output_inventory(
        BOXES, object(),
        detector=lambda i: [_det(200, 500, query="sofa")],
        image_width=1216, image_height=832, output_width=1216, output_height=832)
    assert BOXES == orig_boxes
