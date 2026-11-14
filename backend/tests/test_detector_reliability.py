"""Issue #1B — detector post-processing reliability (coordinate conversion + duplicate
suppression). These lock the VERIFIED-CORRECT behavior of the OWLv2 post-processing helpers
without loading the model: deterministic NMS, order-independence, candidate cap, the
Kitchen repeated-detection behavior, box/center coordinate conversion, and IoU.

(The OWLv2 input-resize / box-to-screen mapping was verified EMPIRICALLY on the real Bedroom 1
output: post_process boxes are identical for target_sizes=original vs square, and align with
the ground-truth furniture positions — i.e. no coordinate-frame corruption. See the Issue #1B
diagnostic. Low recall there is a RENDER-VISIBILITY limit upstream of the detector, not a
coordinate/vocabulary bug.)
"""

from app.services import furniture_geometry_validation_service as geo


def _box(cx, cy, s, w=100.0, h=80.0, q="x"):
    return {"query": q, "score": s, "x": cx - w / 2, "y": cy - h / 2,
            "width": w, "height": h, "center_x": cx, "center_y": cy}


# ── duplicate suppression ───────────────────────────────────────────────────────
def test_nms_suppresses_overlapping_duplicates():
    dets = [_box(100, 100, 0.9), _box(103, 101, 0.8), _box(98, 99, 0.7)]  # same box, 3x
    kept = geo.nms_dedup(dets, nms_iou=0.5)
    assert len(kept) == 1 and kept[0]["score"] == 0.9   # highest-score survivor


def test_nms_keeps_non_overlapping():
    dets = [_box(100, 100, 0.9), _box(400, 400, 0.8), _box(700, 200, 0.7)]
    assert len(geo.nms_dedup(dets, nms_iou=0.5)) == 3


def test_nms_is_order_independent_deterministic():
    dets = [_box(100, 100, 0.9), _box(400, 400, 0.8), _box(700, 200, 0.7), _box(102, 98, 0.6)]
    a = geo.nms_dedup(list(dets))
    b = geo.nms_dedup(list(reversed(dets)))
    assert [(d["center_x"], d["center_y"], d["score"]) for d in a] == \
           [(d["center_x"], d["center_y"], d["score"]) for d in b]


def test_nms_caps_max_candidates():
    dets = [_box(100 + i * 200, 100, 0.9 - i * 0.01) for i in range(10)]  # spread, no overlap
    assert len(geo.nms_dedup(dets, max_candidates=3)) == 3


# ── Kitchen repeated-detection behavior (handled deterministically) ─────────────
def test_kitchen_repeated_detections_collapse_but_distinct_kept():
    # 20 OVERLAPPING "tall cabinet" at one spot + 1 distinct elsewhere.
    dup = [_box(300, 300, 0.50 - i * 0.01, q="a tall cabinet") for i in range(20)]
    distinct = [_box(900, 500, 0.45, q="a tall cabinet")]
    kept = geo.nms_dedup(dup + distinct, nms_iou=0.5)
    assert len(kept) == 2                                   # overlaps collapse to 1; distinct kept
    assert kept[0]["score"] == 0.50 and kept[1]["center_x"] == 900


# ── coordinate conversion / box scaling (no coordinate-frame corruption) ────────
def test_box_center_and_xywh_conversion():
    b = _box(600, 400, 0.9, w=200, h=120)
    assert geo._center(b) == (600, 400)
    x, y, w, h = geo._xywh(b)
    assert (x, y, w, h) == (500.0, 340.0, 200.0, 120.0)
    # box stays within a 1216x832 frame (no overflow / negative after conversion)
    assert 0 <= x and x + w <= 1216 and 0 <= y and y + h <= 832


def test_center_falls_back_to_bbox_when_no_center_fields():
    b = {"x": 100.0, "y": 50.0, "width": 40.0, "height": 20.0}
    assert geo._center(b) == (120.0, 60.0)


def test_iou_identical_and_disjoint():
    a = _box(100, 100, 0.9)
    assert geo.iou(a, a) == 1.0
    assert geo.iou(_box(100, 100, 0.9), _box(900, 700, 0.9)) == 0.0


def test_nms_preserves_query_label():
    kept = geo.nms_dedup([_box(300, 300, 0.7, q="a chest of drawers")])
    assert kept[0]["query"] == "a chest of drawers"   # labels pass through unchanged
