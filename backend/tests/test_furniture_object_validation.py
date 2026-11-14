"""Task 8 — object-level AI geometry validator. Deterministic unit tests with an INJECTED
stub detector (no OWLv2, no FAL, no network). Proves cost-based one-to-one matching, the
PASS/FAIL/UNCERTAIN rules (missing/low-conf/ambiguous => UNCERTAIN, never FAIL), ordering,
scale, duplicate/extra, opening + rotation NOT_VALIDATABLE, deterministic assignment, and
the canonical-invariance guarantee.
"""

import copy

from app.services import furniture_object_validation_service as ov

W, H = 1216, 832  # diag ~1472.9 => gate~412.4, pass~88.4, fail~294.6


def _b(uid, item, cx, cy, w=200.0, h=120.0, room="Bedroom 1", rotation=0.0):
    return {"uid": uid, "item_id": item, "room": room, "rotation": rotation,
            "x": cx - w / 2, "y": cy - h / 2, "width": w, "height": h, "center_x": cx, "center_y": cy}


def _op(uid, item, cx, cy, wall, norm, w=110.0, h=200.0, room="Bedroom 1"):
    return {"uid": uid, "item_id": item, "room": room, "wall": wall, "normalized_wall_position": norm,
            "rotation": 0.0, "x": cx - w / 2, "y": cy - h / 2, "width": w, "height": h,
            "center_x": cx, "center_y": cy}


def _d(cx, cy, w=200.0, h=120.0, score=0.9, query="furniture"):
    return {"query": query, "score": score, "x": cx - w / 2, "y": cy - h / 2,
            "width": w, "height": h, "center_x": cx, "center_y": cy}


def _run(base, dets, openings=None):
    return ov.run_object_validation(base, openings, object(), image_width=W, image_height=H,
                                    detector=lambda _img: dets)


def _st(rep, uid):
    return next(o for o in rep["objects"] if o["uid"] == uid)["status"]


# 1 — one-to-one matching (nearest wins; distractor is an extra, not a double match)
def test_one_to_one_matching():
    base = [_b("l", "side-table", 400, 450), _b("r", "side-table", 800, 450)]
    dets = [_d(802, 452), _d(398, 448), _d(60, 60, score=0.3)]
    rep = _run(base, dets)
    assert _st(rep, "l") == "PASS" and _st(rep, "r") == "PASS"
    # each base matched a DIFFERENT detection
    centers = {tuple(o["ai_center"]) for o in rep["objects"]}
    assert len(centers) == 2


# 2 — duplicate detections: a 2nd STRONG unassignable detection is flagged FOR REVIEW and
# downgrades the scene to UNCERTAIN, but confidence ALONE never proves an extra => never FAIL.
def test_duplicate_detection_is_review_not_fail():
    base = [_b("bed", "bed", 600, 430)]
    dets = [_d(602, 432, score=0.9, query="a bed"), _d(610, 438, score=0.9, query="a bed")]
    rep = _run(base, dets)
    assert any(e["classification"] == "EXTRA_CANDIDATE_REVIEW" for e in rep["extras"])
    assert rep["overall_status"] == "UNCERTAIN"  # downgraded, NOT failed on confidence alone


# 3 — missing detection (no reliable detection at all) => UNCERTAIN, never FAIL
def test_missing_detection_is_uncertain():
    base = [_b("bed", "bed", 600, 430)]
    rep = _run(base, [])  # detector found nothing
    assert _st(rep, "bed") == "UNCERTAIN" and rep["overall_status"] == "UNCERTAIN"
    # a far but WEAK stray detection must also not force FAIL (ambiguous, not a proven extra)
    rep2 = _run(base, [_d(60, 60, score=0.1)])
    assert _st(rep2, "bed") == "UNCERTAIN" and rep2["overall_status"] == "UNCERTAIN"


# 4 — low-confidence detection (aligned but weak) => UNCERTAIN
def test_low_confidence_is_uncertain():
    base = [_b("bed", "bed", 600, 430)]
    rep = _run(base, [_d(601, 431, score=0.1)])
    assert _st(rep, "bed") == "UNCERTAIN"


# 5 — wrong-room / far candidate is not matched => object UNCERTAIN; room carried from base
def test_wrong_room_candidate_uncertain_and_room_preserved():
    base = [_b("bed", "bed", 300, 300, room="Bedroom 1")]
    rep = _run(base, [_d(1150, 780, score=0.9)])  # far away (other side)
    o = next(o for o in rep["objects"] if o["uid"] == "bed")
    assert o["room"] == "Bedroom 1" and o["status"] == "UNCERTAIN"


# 6 — large center displacement with a SAME-TYPE (identity-supported) strong detection => FAIL
def test_large_center_displacement_fail():
    base = [_b("bed", "bed", 400, 430)]
    rep = _run(base, [_d(740, 430, score=0.9, query="a bed")])  # 340px: within gate(412), > fail(295)
    assert _st(rep, "bed") == "FAIL" and rep["overall_status"] == "FAIL"


# 6b — SAME displacement but a WRONG-TYPE detection => UNCERTAIN (probable mis-assignment), not FAIL
def test_displacement_wrong_type_is_uncertain_not_fail():
    base = [_b("bed", "bed", 400, 430)]
    rep = _run(base, [_d(740, 430, score=0.9, query="a chair")])  # confident but not a bed
    o = next(o for o in rep["objects"] if o["uid"] == "bed")
    assert o["status"] == "UNCERTAIN" and o["identity_supported"] is False


# 7 — gross scale change with a same-type strong detection => FAIL
def test_large_scale_change_fail():
    base = [_b("bed", "bed", 600, 430, 200, 120)]
    rep = _run(base, [_d(600, 430, 820, 500, score=0.9, query="a bed")])  # lin-scale ~4 > FAIL_SCALE_HI
    assert _st(rep, "bed") == "FAIL"


# 8 — relative-ordering reversal vs the anchor (both reliable, same-type) => FAIL
def test_ordering_reversal_fail():
    base = [_b("bed", "bed", 600, 430, 300, 220), _b("st", "side-table", 520, 430, 90, 90)]  # st LEFT of bed
    dets = [_d(600, 430, 300, 220, score=0.9, query="a bed"),
            _d(680, 430, 90, 90, score=0.9, query="a side table")]  # st now RIGHT of bed
    rep = _run(base, dets)
    st = next(o for o in rep["objects"] if o["uid"] == "st")
    assert "VIOLATED" in st["ordering_status"] and st["status"] == "FAIL"


# 9 — moderate ambiguous offset (matched, strong, between pass & fail) => UNCERTAIN, never PASS/FAIL
def test_moderate_offset_uncertain():
    base = [_b("bed", "bed", 600, 430)]
    rep = _run(base, [_d(760, 430, score=0.9)])  # 160px: > pass(88), < fail(295)
    assert _st(rep, "bed") == "UNCERTAIN"


# 10 — identical boxes, strong => PASS
def test_identical_boxes_pass():
    base = [_b("bed", "bed", 600, 430)]
    rep = _run(base, [_d(600, 430, score=0.9)])
    assert _st(rep, "bed") == "PASS" and rep["overall_status"] == "PASS"


# 11 — multiple same-type furniture: each matched one-to-one to its own detection
def test_multiple_same_type_one_to_one():
    base = [_b("a", "side-table", 300, 450, 90, 90), _b("b", "side-table", 900, 450, 90, 90)]
    dets = [_d(898, 452, 90, 90), _d(302, 448, 90, 90)]
    rep = _run(base, dets)
    assert _st(rep, "a") == "PASS" and _st(rep, "b") == "PASS"
    assert next(o for o in rep["objects"] if o["uid"] == "a")["ai_center"] != \
           next(o for o in rep["objects"] if o["uid"] == "b")["ai_center"]


# 12 — opening wall association is NOT_VALIDATABLE; opening status never PASS here
def test_opening_wall_not_validatable():
    base = [_b("bed", "bed", 600, 430)]
    ops = [_op("door-1", "door", 860, 820, "wall_077", 0.8603),
           _op("win-1", "window", 330, 676, "wall_086", 0.478858)]
    rep = _run(base, [_d(601, 431, score=0.9)], openings=ops)
    for o in rep["openings"]:
        assert o["ai_wall_association"] == "NOT_VALIDATABLE"
        assert o["status"] != "PASS"
        assert o["wall"] in ("wall_077", "wall_086")
    assert rep["openings"][0]["normalized_wall_position"] in (0.8603, 0.478858)


# 13 — rotation is never claimed from axis-aligned boxes
def test_rotation_not_validatable():
    base = [_b("bed", "bed", 600, 430, rotation=-90.0)]
    rep = _run(base, [_d(600, 430, score=0.9)])
    assert next(o for o in rep["objects"] if o["uid"] == "bed")["rotation_status"] == "NOT_VALIDATABLE"


# 14 — deterministic assignment: detection ORDER must not change the outcome
def test_deterministic_regardless_of_detection_order():
    base = [_b("l", "side-table", 400, 450), _b("r", "side-table", 800, 450)]
    d1 = [_d(802, 452), _d(398, 448)]
    d2 = list(reversed(d1))
    r1 = _run(base, d1)
    r2 = _run(base, d2)
    g1 = {o["uid"]: (o["status"], tuple(o["ai_center"])) for o in r1["objects"]}
    g2 = {o["uid"]: (o["status"], tuple(o["ai_center"])) for o in r2["objects"]}
    assert g1 == g2


# 15 — the validator NEVER mutates the canonical/base inputs
def test_canonical_inputs_unchanged():
    base = [_b("bed", "bed", 600, 430), _b("st", "side-table", 400, 450)]
    ops = [_op("door-1", "door", 860, 820, "wall_077", 0.8603)]
    base_before = copy.deepcopy(base); ops_before = copy.deepcopy(ops)
    _run(base, [_d(601, 431, score=0.9), _d(402, 452, score=0.9)], openings=ops)
    assert base == base_before and ops == ops_before


# registry: anchor is the largest-area object; relative ordering tokens are correct
def test_registry_anchor_and_relative_positions():
    base = [_b("bed", "bed", 600, 430, 300, 220), _b("st", "side-table", 400, 430, 90, 90)]
    reg = ov.build_object_registry(base, [], image_width=W, image_height=H)
    assert reg["anchor_uid"] == "bed"
    st = next(o for o in reg["objects"] if o["uid"] == "st")
    assert st["relative_position"]["horizontal"] == "left"  # 400 < 600


# NOT_VALIDATABLE guards
def test_not_validatable_no_base():
    assert ov.run_object_validation([], None, object(), detector=lambda _i: [])["overall_status"] == "NOT_VALIDATABLE"


def test_not_validatable_no_image():
    assert ov.run_object_validation([_b("bed", "bed", 600, 430)], None, None,
                                    detector=lambda _i: [])["overall_status"] == "NOT_VALIDATABLE"


def test_not_validatable_detector_unavailable():
    def _boom(_i):
        raise RuntimeError("owlv2 missing")
    assert ov.run_object_validation([_b("bed", "bed", 600, 430)], None, object(),
                                    detector=_boom)["overall_status"] == "NOT_VALIDATABLE"


# gating status is NOT_CALIBRATED by default (audit-only; never claims calibrated gating)
def test_gating_status_not_calibrated_by_default():
    rep = _run([_b("bed", "bed", 600, 430)], [_d(600, 430, score=0.9)])
    assert rep["gating_status"] == "NOT_CALIBRATED"


# 7 (STEP E) — a NEARBY but WRONG-type, non-overlapping, beyond-fail-tol detection must NOT be
# accepted as a valid match: the pairing dissolves => base is MISSING, detection returns to extras.
def test_nearby_wrong_type_not_accepted_as_match():
    base = [_b("bed", "bed", 600, 430, 200, 120)]
    # 320px away (within the 412px gate, but > fail_tol 295), zero overlap, wrong type.
    rep = _run(base, [_d(920, 430, 200, 120, score=0.9, query="a floor lamp")])
    o = next(o for o in rep["objects"] if o["uid"] == "bed")
    assert o["status"] == "UNCERTAIN" and o["missing"] is True     # not accepted as a match
    assert o["ai_bbox"] is None                                     # no match claimed
    assert any(e.get("dissolved_from_base") for e in rep["extras"])  # detection returned to extras
    assert rep["overall_status"] != "PASS"


# 9 (STEP E) — Dining Area hallucination: base has ONE dining table; AI adds a table + two chairs.
# The extra chairs must be surfaced as EXTRA_CANDIDATEs and the scene must NOT be PASS.
def test_dining_hallucination_extras_not_pass():
    base = [_b("dt", "dining-table", 450, 400, 320, 150)]
    dets = [_d(455, 405, 320, 150, score=0.9, query="a dining table"),  # real table (matched)
            _d(700, 470, 70, 70, score=0.9, query="a chair"),            # hallucinated
            _d(250, 470, 70, 70, score=0.9, query="a chair")]            # hallucinated
    rep = _run(base, dets)
    assert rep["furniture_counts"]["extra_candidates"] == 2
    assert rep["overall_status"] != "PASS"
    assert rep["furniture_overall"] != "PASS"
