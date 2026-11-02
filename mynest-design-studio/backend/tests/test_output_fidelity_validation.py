"""Step 2U — OUTPUT-level furniture-fidelity validation (offline; stub detector; no OWLv2/paid).

Exercises the EXISTING output validators against the generated-image side (not just the input
design), proving they:
  * flag MISSING canonical objects (never a silent pass),
  * flag EXTRA/hallucinated detections,
  * return NOT_VALIDATABLE when the detector/image is unavailable (never PASS),
  * never report a missing/extra scene as overall PASS,
and that the honest geometry-status chain can never mark such an output FAITHFUL.
All detections are injected stubs — no vision model is downloaded or run, no paid calls.
"""
from __future__ import annotations

from app.services import furniture_object_validation_service as OBJ
from app.services import furniture_geometry_validation_service as GEO
from app.services import validation_service as V


def _base(uid, item_id, x, y, w=160, h=90, room="Living Area"):
    return {"uid": uid, "item_id": item_id, "x": x, "y": y, "width": w, "height": h, "room": room}


def _det(x, y, w=160, h=90, query="sofa", score=0.9):
    return {"x": x, "y": y, "width": w, "height": h, "query": query, "score": score}


BASE = [_base("sofa-1", "lounger-sofa", 200, 500), _base("console-1", "console", 800, 520, 150, 60)]
REG = OBJ.build_object_registry(BASE)


# ── run_geometry_validation graceful NOT_VALIDATABLE (never PASS) ──────────────

def test_not_validatable_without_base_or_image():
    assert GEO.run_geometry_validation([], None)["overall_status"] == "NOT_VALIDATABLE"
    assert GEO.run_geometry_validation(BASE, None)["overall_status"] == "NOT_VALIDATABLE"


def test_detector_unavailable_is_not_validatable_never_pass():
    def _boom(_img):
        raise RuntimeError("owlv2 weights not installed")
    r = GEO.run_geometry_validation(BASE, object(), detector=_boom)
    assert r["overall_status"] == "NOT_VALIDATABLE"
    assert "detector unavailable" in r["reason"]


# ── validate_objects distinguishes missing / extra / present ──────────────────

def test_missing_object_is_flagged_not_silently_passed():
    # only the console is detected; the sofa has NO detection -> MISSING/UNCERTAIN
    ai = [_det(800, 520, 150, 60, query="console")]
    r = OBJ.validate_objects(REG, ai)
    assert r["missing_count"] >= 1
    assert r["overall_status"] != "PASS"            # a missing object can never be a PASS
    sofa = next(o for o in r["objects"] if o["uid"] == "sofa-1")
    assert sofa.get("missing") is True and sofa["status"] == "UNCERTAIN"


def test_extra_detection_is_flagged_and_downgrades_pass():
    # both base objects detected, PLUS a hallucinated extra far from everything
    ai = [_det(200, 500, query="sofa"), _det(800, 520, 150, 60, query="console"),
          _det(1100, 120, 120, 120, query="floor lamp", score=0.95)]
    r = OBJ.validate_objects(REG, ai)
    assert r["extra_candidate_count"] >= 1
    assert r["overall_status"] != "PASS"            # an unexplained extra is never a clean PASS


def test_no_detections_all_missing_not_pass():
    r = OBJ.validate_objects(REG, [])
    assert r["overall_status"] != "PASS"
    assert r["missing_count"] == len(REG["objects"])


# ── honest status chain: missing/extra output can never be FAITHFUL ───────────

def test_missing_or_extra_output_cannot_be_reported_faithful():
    # Even if an output check were (wrongly) marked verified, an edit-path (no structural
    # conditioning) render stays UNVERIFIED; and with no output verification it is UNVERIFIED.
    unver = V.assess_ai_render(used_base_render=True, scene_report={"geometry_faithful": True},
                               output_verified=False, structural_conditioning=False)
    assert unver["geometry_status"] == "UNVERIFIED"
    edit_even_if_verified = V.assess_ai_render(used_base_render=True,
                                               scene_report={"geometry_faithful": True},
                                               output_verified=True, structural_conditioning=False)
    assert edit_even_if_verified["geometry_status"] == "UNVERIFIED"  # edit path never FAITHFUL
