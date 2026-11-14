"""Advisory object-level AI GEOMETRY validation — matcher + status logic.

Deterministic unit tests: the open-vocabulary detector is INJECTED (a stub), so OWLv2 is
not needed here. Proves one-to-one spatial matching, PASS/FAIL/UNCERTAIN/NOT_VALIDATABLE,
missing/duplicate handling, relative ordering, and opening wall passthrough. This layer
is SEPARATE from inventory validation and never converts uncertainty into PASS.
"""

from app.services import furniture_geometry_validation_service as geo

W, H = 1216, 832


def _b(uid, item, cx, cy, w=200.0, h=120.0):
    return {"uid": uid, "item_id": item, "x": cx - w / 2, "y": cy - h / 2,
            "width": w, "height": h, "center_x": cx, "center_y": cy}


def _d(cx, cy, w=200.0, h=120.0, score=0.9, query="x"):
    return {"query": query, "score": score, "x": cx - w / 2, "y": cy - h / 2,
            "width": w, "height": h, "center_x": cx, "center_y": cy}


def _status(rep, uid):
    return next(o for o in rep["objects"] if o["uid"] == uid)["match_status"]


# ── matcher primitives ────────────────────────────────────────────────────────

def test_iou_and_center_distance():
    a = _b("a", "bed", 600, 430)
    assert geo.iou(a, a) == 1.0
    assert geo.center_distance(a, _b("b", "bed", 600, 430)) == 0.0
    assert round(geo.center_distance(a, _b("b", "bed", 603, 434)), 1) == 5.0


def test_assignment_is_one_to_one_no_double_count():
    base = [_b("l", "side-table", 400, 450), _b("r", "side-table", 700, 450)]
    ai = [_d(702, 452), _d(398, 448), _d(1100, 100)]  # 2 near + 1 far distractor
    asn = geo.optimal_assignment(base, ai, gate=400)
    assert asn == {0: 1, 1: 0}  # l→ai[1], r→ai[0]; distractor unused
    assert len(set(asn.values())) == len(asn)


# ── per-object status ──────────────────────────────────────────────────────────

def test_aligned_boxes_pass():
    base = [_b("bed", "bed", 600, 430)]
    rep = geo.compare_geometry(base, [_d(604, 433)], image_width=W, image_height=H)
    assert _status(rep, "bed") == "PASS" and rep["overall_status"] == "PASS"


def test_large_displacement_fail():
    # matched within gate (0.28*diag≈412) but beyond fail tol (0.20*diag≈295), high conf
    base = [_b("bed", "bed", 400, 430)]
    rep = geo.compare_geometry(base, [_d(730, 430, score=0.9)], image_width=W, image_height=H)
    bed = next(o for o in rep["objects"] if o["uid"] == "bed")
    assert bed["match_status"] == "FAIL" and rep["overall_status"] == "FAIL"


def test_moderate_offset_uncertain():
    # offset between pass (≈88px) and fail (≈295px) → UNCERTAIN, never PASS
    base = [_b("bed", "bed", 600, 430)]
    rep = geo.compare_geometry(base, [_d(760, 430, score=0.9)], image_width=W, image_height=H)
    assert _status(rep, "bed") == "UNCERTAIN" and rep["overall_status"] == "UNCERTAIN"


def test_low_confidence_match_uncertain_not_pass():
    base = [_b("bed", "bed", 600, 430)]
    rep = geo.compare_geometry(base, [_d(604, 433, score=0.1)], image_width=W, image_height=H)
    assert _status(rep, "bed") == "UNCERTAIN"  # positionally aligned but detector too weak


def test_missing_object_is_uncertain_not_fail():
    # base object with no AI detection within the gate → UNCERTAIN (cannot prove absent)
    base = [_b("bed", "bed", 600, 430)]
    rep = geo.compare_geometry(base, [_d(60, 60)], image_width=W, image_height=H)
    assert _status(rep, "bed") == "UNCERTAIN" and rep["overall_status"] == "UNCERTAIN"


def test_extra_ai_boxes_reported_not_failed_by_default():
    base = [_b("bed", "bed", 600, 430)]
    rep = geo.compare_geometry(base, [_d(604, 433), _d(1100, 700, query="chair")],
                               image_width=W, image_height=H)
    assert _status(rep, "bed") == "PASS"
    assert any(e.get("query") == "chair" for e in rep["extra_ai_boxes"])


def test_relative_ordering_preserved_both_pass():
    base = [_b("l", "side-table", 400, 450, 90, 90), _b("r", "side-table", 700, 450, 90, 90)]
    ai = [_d(702, 452, 90, 90), _d(398, 448, 90, 90)]
    rep = geo.compare_geometry(base, ai, image_width=W, image_height=H)
    assert _status(rep, "l") == "PASS" and _status(rep, "r") == "PASS"
    assert rep["overall_status"] == "PASS"


# ── NOT_VALIDATABLE ──────────────────────────────────────────────────────────

def test_not_validatable_no_base():
    rep = geo.run_geometry_validation([], _d(0, 0), detector=lambda img: [])
    assert rep["overall_status"] == "NOT_VALIDATABLE"


def test_not_validatable_no_ai_image():
    rep = geo.run_geometry_validation([_b("bed", "bed", 600, 430)], None, detector=lambda img: [])
    assert rep["overall_status"] == "NOT_VALIDATABLE"


def test_not_validatable_detector_unavailable():
    def _boom(_img):
        raise RuntimeError("owlv2 missing")
    rep = geo.run_geometry_validation([_b("bed", "bed", 600, 430)], object(), detector=_boom)
    assert rep["overall_status"] == "NOT_VALIDATABLE"


# ── orchestrator with an injected detector (no OWLv2) ────────────────────────

def test_run_with_injected_detector_pass():
    base = [_b("bed", "bed", 600, 430)]
    rep = geo.run_geometry_validation(base, object(), detector=lambda img: [_d(602, 432)])
    assert rep["overall_status"] == "PASS" and rep["detector"] == "injected"


# ── openings: wall/room carried, AI wall never inferred ──────────────────────

def test_openings_carry_wall_and_never_infer_ai_wall():
    base_op = [{"uid": "door-1", "item_id": "door", "room": "Bedroom 1", "wall": "wall_077",
                "x": 640, "y": 337, "width": 110, "height": 203, "center_x": 695, "center_y": 438,
                "normalized_wall_position": 0.86}]
    rep = geo.compare_openings(base_op, [_d(697, 440, 110, 203)], image_width=W, image_height=H)
    o = rep["objects"][0]
    assert o["type"] == "door" and o["room"] == "Bedroom 1" and o["wall"] == "wall_077"
    assert o["normalized_wall_position"] == 0.86
    assert o["ai_wall_association"] == "NOT_VALIDATABLE"  # never inferred from pixels/furniture
