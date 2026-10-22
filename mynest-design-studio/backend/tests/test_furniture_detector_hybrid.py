"""Issue #1B — hybrid detector (COCO YOLO + OWLv2): class-aware cross-source dedup,
input immutability, deterministic tie-breaking, provenance, and distinguishable failure
reporting. Deterministic unit tests; YOLO/OWLv2 are mocked so no model loads."""

import copy
from unittest import mock

from app.services import furniture_detector_hybrid as hy


def _box(cx, cy, s, w=100.0, h=80.0, q="x", source=None, **extra):
    d = {"query": q, "score": s, "x": cx - w / 2, "y": cy - h / 2, "width": w, "height": h,
         "center_x": cx, "center_y": cy, **extra}
    if source is not None:
        d["source"] = source
    return d


# ── COCO class mapping only covers furniture/appliances ─────────────────────────
def test_coco_mapping_is_furniture_only():
    m = hy.COCO_FURNITURE_TO_LABEL
    assert m["bed"] == "bed" and m["couch"] == "sofa" and m["dining table"] == "dining table"
    assert m["refrigerator"] == "refrigerator" and m["oven"] == "oven" and m["sink"] == "sink"
    for non_furniture in ("person", "car", "dog", "traffic light"):
        assert non_furniture not in m


# ── class families (used by class-aware dedup) ──────────────────────────────────
def test_class_family_grouping():
    assert hy._class_family("a tall cabinet") == "kitchen_cabinet"
    assert hy._class_family("kitchen counter") == "kitchen_cabinet"
    assert hy._class_family("refrigerator") == "refrigerator"
    assert hy._class_family("a bedside table") == "side_table"
    assert hy._class_family("a chest of drawers") == "dresser"
    assert hy._class_family("couch") == "sofa"


# ── SAME-class overlap collapses to the higher-confidence candidate ─────────────
def test_merge_same_class_overlap_collapses_keep_higher():
    yolo = [_box(300, 300, 0.80, q="refrigerator", source="yolo-coco")]
    owl = [_box(305, 302, 0.40, q="refrigerator")]  # same family, overlapping
    merged = hy.merge_candidates(yolo, owl, cross_iou=0.5)
    assert len(merged) == 1 and merged[0]["source"] == "yolo-coco" and merged[0]["score"] == 0.80


# ── DIFFERENT-class overlap is NOT suppressed (both identity hypotheses kept) ───
def test_merge_different_class_overlap_both_kept():
    yolo = [_box(300, 300, 0.80, q="refrigerator", source="yolo-coco")]
    owl = [_box(305, 302, 0.45, q="a tall cabinet")]  # overlaps, DIFFERENT family
    merged = hy.merge_candidates(yolo, owl, cross_iou=0.5)
    assert len(merged) == 2
    fams = {hy._class_family(d["query"]) for d in merged}
    assert fams == {"refrigerator", "kitchen_cabinet"}


# ── distinct nearby same-class items (low IoU) preserved ────────────────────────
def test_merge_keeps_distinct_nearby_same_class():
    a = [_box(200, 300, 0.8, q="a side table", source="owlv2")]
    b = [_box(900, 300, 0.7, q="a side table", source="owlv2")]  # far apart, no overlap
    merged = hy.merge_candidates([], a + b, cross_iou=0.6)
    assert len(merged) == 2


# ── cross-source duplicate of the same object collapses ─────────────────────────
def test_merge_cross_source_duplicate_collapses():
    yolo = [_box(400, 400, 0.6, q="bed", source="yolo-coco")]
    owl = [_box(402, 399, 0.9, q="a bed")]  # same family, overlap, higher conf
    merged = hy.merge_candidates(yolo, owl, cross_iou=0.5)
    assert len(merged) == 1 and merged[0]["source"] == "owlv2" and merged[0]["score"] == 0.9


# ── equal-confidence tie-break is deterministic (order-independent) ─────────────
def test_merge_equal_confidence_tie_break_deterministic():
    dets = [_box(200, 300, 0.5, q="a side table", source="owlv2"),
            _box(900, 300, 0.5, q="a tall cabinet", source="owlv2"),
            _box(500, 600, 0.5, q="bed", source="yolo-coco")]
    a = hy.merge_candidates([], list(dets))
    b = hy.merge_candidates([], list(reversed(dets)))
    key = lambda L: [(d["center_x"], d["center_y"], hy._class_family(d["query"])) for d in L]
    assert key(a) == key(b)


# ── inputs are NOT mutated ──────────────────────────────────────────────────────
def test_merge_does_not_mutate_inputs():
    yolo = [_box(300, 300, 0.8, q="refrigerator", source="yolo-coco")]
    owl = [_box(900, 500, 0.4, q="a side table")]       # NOTE: no 'source' key on input
    yolo_before, owl_before = copy.deepcopy(yolo), copy.deepcopy(owl)
    hy.merge_candidates(yolo, owl)
    assert yolo == yolo_before and owl == owl_before      # unchanged; no source injected


def test_merge_caps_max_candidates():
    dets = [_box(100 + i * 180, 100, 0.9 - i * 0.01, q=f"item{i}") for i in range(10)]
    assert len(hy.merge_candidates([], dets, max_candidates=3)) == 3


# ── detect_hybrid: union with provenance ────────────────────────────────────────
def test_detect_hybrid_unions_both_sources():
    fy = [_box(300, 300, 0.75, q="refrigerator", source="yolo-coco")]
    fo = [_box(900, 500, 0.30, q="a side table")]
    with mock.patch.object(hy, "detect_yolo_coco", return_value=fy):
        out = hy.detect_hybrid("fake.png", owl_detector=lambda _i: fo)
    assert {d["source"] for d in out} == {"yolo-coco", "owlv2"}
    assert any(d["query"] == "refrigerator" for d in out)


# ── failure reporting: YOLO zero vs unavailable vs inference-failure; OWLv2 outage ──
def test_status_yolo_success_with_zero_detections():
    with mock.patch.object(hy, "detect_yolo_coco", return_value=[]):
        _out, st = hy.detect_hybrid_with_status("fake.png", owl_detector=lambda _i: [_box(1, 1, 0.3)])
    assert st["yolo_status"] == "SUCCESS_ZERO" and st["yolo_count"] == 0 and st["owlv2_status"] == "SUCCESS"
    assert st["merge"] == "COMPLETED"


def test_status_yolo_detections():
    with mock.patch.object(hy, "detect_yolo_coco", return_value=[_box(2, 2, 0.8, q="bed", source="yolo-coco")]):
        _out, st = hy.detect_hybrid_with_status("fake.png", owl_detector=lambda _i: [])
    assert st["yolo_status"] == "SUCCESS_WITH_DETECTIONS" and st["yolo_count"] == 1


def test_status_yolo_unavailable_is_not_zero():
    with mock.patch.object(hy, "detect_yolo_coco", side_effect=ImportError("no ultralytics")):
        out, st = hy.detect_hybrid_with_status("fake.png", owl_detector=lambda _i: [_box(1, 1, 0.3)])
    assert st["yolo_status"] == "UNAVAILABLE" and out  # OWLv2-only fallback still returns results


def test_status_yolo_inference_failure_distinct_from_zero():
    with mock.patch.object(hy, "detect_yolo_coco", side_effect=RuntimeError("cuda oom")):
        _out, st = hy.detect_hybrid_with_status("fake.png", owl_detector=lambda _i: [_box(1, 1, 0.3)])
    assert st["yolo_status"] == "INFERENCE_FAILURE"  # NOT silently a zero-detection result


def test_owlv2_outage_reraises_not_zero():
    def _boom(_i):
        raise RuntimeError("owlv2 down")
    import pytest
    with mock.patch.object(hy, "detect_yolo_coco", return_value=[]):
        with pytest.raises(RuntimeError):
            hy.detect_hybrid_with_status("fake.png", owl_detector=_boom)


# ── hardening: class-compatibility (overlapping DIFFERENT types are NOT merged) ──
import pytest


@pytest.mark.parametrize("qa,qb", [
    ("a side table", "a dining table"),
    ("a console", "a kitchen cabinet"),
    ("refrigerator", "a tall cabinet"),
    ("a chair", "a dining chair"),
    ("a wardrobe", "a bed"),
])
def test_overlapping_incompatible_classes_both_kept(qa, qb):
    a = [_box(400, 400, 0.8, q=qa, source="owlv2")]
    b = [_box(402, 401, 0.7, q=qb, source="yolo-coco")]   # heavily overlapping, different type
    merged = hy.merge_candidates(a, b, cross_iou=0.5)
    assert len(merged) == 2
    assert hy._class_family(qa) != hy._class_family(qb)


def test_overlapping_same_family_aliases_merge():
    a = [_box(400, 400, 0.9, q="a fridge", source="yolo-coco")]
    b = [_box(401, 399, 0.5, q="refrigerator", source="owlv2")]  # same family (refrigerator)
    assert len(hy.merge_candidates(a, b, cross_iou=0.5)) == 1


# ── hardening: word-boundary matching (no broad substring false hits) ───────────
@pytest.mark.parametrize("label,expected_not", [
    ("a woven basket", "oven"),
    ("outdoor furniture", "door"),
    ("a bedside table", "bed"),
])
def test_word_boundary_no_false_family(label, expected_not):
    assert hy._class_family(label) != expected_not


def test_bedside_table_is_side_table():
    assert hy._class_family("a bedside table") == "side_table"


# ── hardening: parameter validation ─────────────────────────────────────────────
@pytest.mark.parametrize("bad", [-0.1, 1.1, 2.0, "x", None])
def test_cross_iou_must_be_unit_interval(bad):
    with pytest.raises(ValueError):
        hy.merge_candidates([], [_box(1, 1, 0.5)], cross_iou=bad)


@pytest.mark.parametrize("bad", [-1, 1.5, "3", True, None])
def test_max_candidates_must_be_nonneg_int(bad):
    with pytest.raises(ValueError):
        hy.merge_candidates([], [_box(1, 1, 0.5)], max_candidates=bad)


def test_boundary_cross_iou_and_zero_max_candidates():
    dets = [_box(100, 100, 0.9), _box(400, 400, 0.8)]
    assert hy.merge_candidates([], list(dets), cross_iou=0.0) is not None   # 0 is valid
    assert hy.merge_candidates([], list(dets), cross_iou=1.0) is not None   # 1 is valid
    assert hy.merge_candidates([], list(dets), max_candidates=0) == []       # 0 => empty


# ── hardening: malformed image rejected (NOT silently zero) ─────────────────────
@pytest.mark.parametrize("bad", [123, {"not": "an image"}, 4.5])
def test_malformed_image_raises_not_silent_zero(bad):
    with pytest.raises(TypeError):
        hy.detect_hybrid_with_status(bad, owl_detector=lambda _i: [])


def test_valid_str_image_is_accepted():
    out = hy.detect_hybrid("fake.png", owl_detector=lambda _i: [_box(1, 1, 0.3)])
    with mock.patch.object(hy, "detect_yolo_coco", return_value=[]):
        out = hy.detect_hybrid("fake.png", owl_detector=lambda _i: [_box(1, 1, 0.3)])
    assert isinstance(out, list)


# ── hardening: full permutation determinism (equal confidence) ──────────────────
def test_full_permutation_equal_confidence_is_stable():
    import itertools
    base = [_box(200, 300, 0.5, q="a side table", source="owlv2"),
            _box(900, 300, 0.5, q="a tall cabinet", source="yolo-coco"),
            _box(500, 600, 0.5, q="bed", source="yolo-coco"),
            _box(300, 300, 0.5, q="a dining table", source="owlv2")]
    outs = set()
    for perm in itertools.permutations(base):
        m = hy.merge_candidates([], list(perm))
        outs.add(tuple((d["center_x"], d["center_y"], hy._class_family(d["query"]), d["source"]) for d in m))
    assert len(outs) == 1   # identical output for every input permutation


# ════════════════════════════════════════════════════════════════════════════════
# Final edge-case fixes (Issue #1B)
# ════════════════════════════════════════════════════════════════════════════════
import io as _io
import math as _math
from pathlib import Path as _Path

import numpy as _np
from PIL import Image as _PILImage


# 1 — class-family audit: distinct semantic classes stay SEPARATE
@pytest.mark.parametrize("qa,fa,qb,fb", [
    ("a vase", "vase", "a potted plant", "plant"),
    ("bay window seating", "bench", "a bay window", "window"),
    ("a table", "table", "a dining table", "dining_table"),
    ("a table", "table", "a side table", "side_table"),
    ("a chair", "chair", "a dining chair", "dining_chair"),
])
def test_distinct_classes_have_distinct_families(qa, fa, qb, fb):
    assert hy._class_family(qa) == fa
    assert hy._class_family(qb) == fb
    assert fa != fb


def test_overlapping_vase_and_plant_both_kept():
    a = [_box(400, 400, 0.8, q="a vase", source="owlv2")]
    b = [_box(402, 401, 0.7, q="a potted plant", source="yolo-coco")]
    assert len(hy.merge_candidates(a, b, cross_iou=0.5)) == 2


# 2 — cross_iou rejects NaN / +inf / -inf / bool; accepts 0.0 and 1.0
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), True, False])
def test_cross_iou_rejects_nonfinite_and_bool(bad):
    with pytest.raises(ValueError):
        hy.merge_candidates([], [_box(1, 1, 0.5)], cross_iou=bad)


def test_cross_iou_accepts_exact_boundaries():
    dets = [_box(100, 100, 0.9), _box(400, 400, 0.8)]
    assert hy.merge_candidates([], list(dets), cross_iou=0.0) is not None
    assert hy.merge_candidates([], list(dets), cross_iou=1.0) is not None


# 3 — image normalization: every accepted input type is normalized consistently
def _png_bytes():
    buf = _io.BytesIO()
    _PILImage.new("RGB", (8, 8), (10, 20, 30)).save(buf, "PNG")
    return buf.getvalue()


def test_normalize_str_and_pathlike():
    assert hy._normalize_image("x/y.png") == "x/y.png"
    assert hy._normalize_image(_Path("x") / "y.png") == str(_Path("x") / "y.png")


def test_normalize_pil_passthrough():
    im = _PILImage.new("RGB", (4, 4))
    assert hy._normalize_image(im) is im


def test_normalize_bytes_via_bytesio():
    out = hy._normalize_image(_png_bytes())
    assert isinstance(out, _PILImage.Image) and out.size == (8, 8)


def test_normalize_ndarray_via_fromarray():
    arr = _np.zeros((6, 10, 3), dtype=_np.uint8)
    out = hy._normalize_image(arr)
    assert isinstance(out, _PILImage.Image) and out.size == (10, 6)


@pytest.mark.parametrize("bad", [123, 4.5, {"not": "image"}, ["list"]])
def test_normalize_rejects_malformed(bad):
    with pytest.raises(TypeError):
        hy._normalize_image(bad)


def test_detect_hybrid_accepts_bytes_and_ndarray_inputs():
    # both encoded bytes and arrays are normalized before reaching the detectors
    with mock.patch.object(hy, "detect_yolo_coco", return_value=[]):
        for img in (_png_bytes(), _np.zeros((6, 6, 3), dtype=_np.uint8)):
            out = hy.detect_hybrid(img, owl_detector=lambda _i: [_box(1, 1, 0.3)])
            assert isinstance(out, list) and len(out) == 1
