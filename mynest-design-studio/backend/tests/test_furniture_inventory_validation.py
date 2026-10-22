"""Post-AI furniture INVENTORY validation (audit stage 8) — multi-stage flow.

Covers the evidence-preserving enumerate (Stage A) -> classify (Stage B) -> reconcile
(D/E) -> adjudicate (F) flow in ``furniture_inventory_validation_service``. Reconciliation
logic is tested directly (model-agnostic); the orchestrator is tested with a MOCKED
NVIDIA vision call routed per stage, so tests are hermetic and make no network request.
Dynamic-expected-inventory, opening-exclusion and canonical-immutability use the real
plan via the existing canonical infrastructure, discovered dynamically (no hardcoded plan
id / room / counts). A real NVIDIA call on the controlled FAL image is a separate runtime
proof, never here.
"""

import copy
import json
from io import BytesIO

import pytest
from PIL import Image

from app.services import floor_plan_service
from app.services import furniture_inventory_validation_service as fiv


# ── dynamic discovery (no hardcoded floor_plan_id / room / counts) ───────────

def _discover_plan_room_with_furniture():
    from app.services import prompt_service
    for fp in floor_plan_service.list_floor_plans():
        try:
            canonical = floor_plan_service.get_canonical(fp.id)
        except Exception:  # noqa: BLE001
            continue
        for label, items in prompt_service.group_by_room(canonical.get("furniture") or []):
            expected = fiv.expected_inventory(items)
            if expected:
                return str(fp.id), canonical, label, items, expected
    pytest.skip("no floor plan with furniture available in this environment")


# ── normalized-object helper (post-classification shape reconcile expects) ───

def _nobj(oid, typ, conf, alts=(), status=None, enum_conf=0.9, desc="", cat=""):
    alts = [a for a in alts if a != typ]
    if status is None:
        status = "UNKNOWN" if typ == "unknown" else ("AMBIGUOUS" if alts else "CONFIDENT")
    return {"object_id": oid, "generic_category": cat, "visual_description": desc,
            "enum_confidence": enum_conf, "type": typ, "raw_type": typ,
            "alternative_types": list(alts), "confidence": conf,
            "classification_status": status}


def _status_of(report, t):
    return next(p for p in report["per_type"] if p["type"] == t)["status"]


_TRISTATE = {"PASS", "FAIL", "UNCERTAIN"}


# ── orchestrator mock harness (routes Stage A / B / F) ───────────────────────

def _img(w: int = 64, h: int = 48) -> Image.Image:
    return Image.new("RGB", (w, h), (123, 200, 90))


class _FakeResp:
    def __init__(self, content, status_code=200):
        self.status_code = status_code
        self._content = content

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


def _enum_content(specs):
    return json.dumps({"objects": [
        {"object_id": s["object_id"], "generic_category": s.get("cat", "furniture"),
         "visual_description": s.get("desc", ""), "confidence": s.get("enum_conf", 0.9)}
        for s in specs]})


def _cls_content(specs):
    return json.dumps({"objects": [
        {"object_id": s["object_id"], "type": s["type"],
         "alternative_types": s.get("alts", []), "confidence": s["conf"]}
        for s in specs]})


def _router(specs, *, adj=None, enum_override=None, cls_override=None, sink=None):
    def _post(url, body, headers):
        text = body["messages"][-1]["content"][0]["text"]
        if sink is not None:
            sink.setdefault("bodies", []).append(body)
        if fiv.ADJUDICATION_MARKER in text:
            return _FakeResp(adj if adj is not None else json.dumps({"objects": []}))
        if fiv.CLASSIFICATION_MARKER in text:
            return _FakeResp(cls_override if cls_override is not None else _cls_content(specs))
        return _FakeResp(enum_override if enum_override is not None else _enum_content(specs))
    return _post


def _run(expected, specs, *, adjudicate=False, conf_threshold=0.5, adj=None, sink=None):
    return fiv.run_inventory_validation(
        _img(), expected, enabled=True, adjudicate=adjudicate, conf_threshold=conf_threshold,
        post=_router(specs, adj=adj, sink=sink))


def _spec(oid, typ, conf, alts=None, desc="", cat="furniture"):
    s = {"object_id": oid, "type": typ, "conf": conf, "desc": desc, "cat": cat}
    if alts is not None:
        s["alts"] = alts
    return s


# ══ Stage-A/B validators ═════════════════════════════════════════════════════

# 1. every physical object is enumerated (none dropped)
def test_every_physical_object_enumerated():
    v = fiv.validate_enumeration({"objects": [
        {"object_id": "obj_001", "confidence": 0.9},
        {"object_id": "obj_002", "confidence": 0.8},
        {"object_id": "obj_003", "confidence": 0.7}]})
    assert v["status"] == "ok" and len(v["objects"]) == 3
    assert all(o["type"] == "unknown" for o in v["objects"])  # not classified yet


# 2. object IDs are unique (duplicate rejected)
def test_duplicate_object_ids_rejected():
    v = fiv.validate_enumeration({"objects": [
        {"object_id": "obj_001", "confidence": 0.9},
        {"object_id": "obj_001", "confidence": 0.8}]})
    assert len(v["objects"]) == 1
    assert any(x["reason"] == "duplicate object_id" for x in v["rejected"])


# 3. unknown taxonomy type remains unknown (never guessed)
def test_unknown_type_remains_unknown():
    objs = fiv.validate_enumeration({"objects": [{"object_id": "obj_001", "confidence": 0.9}]})["objects"]
    fiv.apply_classification(objs, {"objects": [
        {"object_id": "obj_001", "type": "spaceship", "confidence": 0.9}]})
    assert objs[0]["type"] == "unknown" and objs[0]["raw_type"] == "spaceship"


# 4. alternative taxonomy types preserved; classification cannot invent objects
def test_alternatives_preserved_and_no_invented_objects():
    objs = fiv.validate_enumeration({"objects": [{"object_id": "obj_001", "confidence": 0.9}]})["objects"]
    res = fiv.apply_classification(objs, {"objects": [
        {"object_id": "obj_001", "type": "dressing-table", "alternative_types": ["side-table"], "confidence": 0.52},
        {"object_id": "obj_999", "type": "bed", "confidence": 0.9}]})  # not enumerated
    assert objs[0]["alternative_types"] == ["side-table"]
    assert objs[0]["classification_status"] == "AMBIGUOUS"
    assert res["applied"] == 1
    assert any(x["reason"] == "unknown object_id" for x in res["ignored"])


# 13. invalid confidence is rejected in enumeration
def test_invalid_confidence_rejected():
    v = fiv.validate_enumeration({"objects": [
        {"object_id": "obj_001", "confidence": 1.7},
        {"object_id": "obj_002", "confidence": "high"},
        {"object_id": "obj_003", "confidence": 0.9}]})
    assert len(v["objects"]) == 1 and len(v["rejected"]) == 2


# ══ reconcile() — core D/E logic (model-agnostic) ════════════════════════════

# 5. ambiguous object does not disappear
def test_ambiguous_object_does_not_disappear():
    rep = fiv.reconcile({"side-table": 1}, [_nobj("o1", "dressing-table", 0.5, alts=["side-table"])])
    assert rep["ambiguous_objects"] and rep["enumerated_total"] == 1


# 6. one object cannot satisfy two expected types
def test_one_object_cannot_satisfy_two_expected_types():
    rep = fiv.reconcile({"side-table": 1, "dressing-table": 1},
                        [_nobj("o1", "side-table", 0.5, alts=["dressing-table"])])
    assert _status_of(rep, "side-table") == "UNCERTAIN"
    assert _status_of(rep, "dressing-table") == "UNCERTAIN"
    assert rep["overall_status"] == "UNCERTAIN"


# 7. ambiguous side-table/dressing-table reconciliation
def test_ambiguous_side_table_dressing_table_reconciliation():
    rep = fiv.reconcile({"side-table": 2, "dressing-table": 1}, [
        _nobj("o1", "side-table", 1.0),
        _nobj("o2", "dressing-table", 0.52, alts=["side-table"]),
        _nobj("o3", "dressing-table", 1.0)])
    assert _status_of(rep, "side-table") == "UNCERTAIN"
    assert _status_of(rep, "dressing-table") == "PASS"


# 8. confident side-table count = 2 -> PASS
def test_two_confident_side_tables_pass():
    rep = fiv.reconcile({"side-table": 2}, [_nobj("o1", "side-table", 0.95), _nobj("o2", "side-table", 0.9)])
    assert _status_of(rep, "side-table") == "PASS" and rep["overall_status"] == "PASS"


# 9. side-table 1 + ambiguous candidate -> UNCERTAIN
def test_one_side_table_plus_ambiguous_uncertain():
    rep = fiv.reconcile({"side-table": 2}, [
        _nobj("o1", "side-table", 1.0), _nobj("o2", "dressing-table", 0.5, alts=["side-table"])])
    st = next(p for p in rep["per_type"] if p["type"] == "side-table")
    assert st["status"] == "UNCERTAIN" and st["confident_detected_count"] == 1
    assert st["ambiguous_candidate_count"] == 1 and st["possible_count"] == 2


# 10. side-table 1 with no candidate -> UNCERTAIN (classification MISSING)
def test_one_side_table_no_candidate_uncertain():
    rep = fiv.reconcile({"side-table": 2}, [_nobj("o1", "side-table", 1.0)])
    st = next(p for p in rep["per_type"] if p["type"] == "side-table")
    assert st["status"] == "UNCERTAIN" and st["classification"] == "MISSING" and st["possible_count"] == 1


# 11. side-table 3 confidently -> FAIL
def test_three_confident_side_tables_fail():
    rep = fiv.reconcile({"side-table": 2}, [_nobj(f"o{i}", "side-table", 0.95) for i in range(3)])
    assert _status_of(rep, "side-table") == "FAIL" and rep["overall_status"] == "FAIL"


# 12. extra furniture -> FAIL
def test_confident_extra_furniture_fail():
    rep = fiv.reconcile({"bed": 1}, [_nobj("o1", "bed", 0.95), _nobj("o2", "lounger-sofa", 0.95)])
    assert _status_of(rep, "lounger-sofa") == "FAIL" and rep["overall_status"] == "FAIL"


# 14. low confidence -> UNCERTAIN
def test_low_confidence_uncertain():
    rep = fiv.reconcile({"bed": 1}, [_nobj("o1", "bed", 0.2, status="CONFIDENT")])
    bed = next(p for p in rep["per_type"] if p["type"] == "bed")
    assert bed["status"] == "UNCERTAIN" and bed["confident_detected_count"] == 0


# 20. per-type status strictly PASS/FAIL/UNCERTAIN; expected count never forces a type
def test_per_type_status_is_strictly_tristate_and_no_forcing():
    cases = [
        ({"bed": 1}, [_nobj("o1", "bed", 0.9)]),
        ({"bed": 1}, [_nobj("o1", "bed", 0.9), _nobj("o2", "wardrobe", 0.9)]),
        ({"side-table": 2}, [_nobj("o1", "side-table", 0.9)]),
        ({"side-table": 2}, [_nobj(f"o{i}", "side-table", 0.9) for i in range(3)]),
    ]
    for expected, objs in cases:
        rep = fiv.reconcile(expected, objs)
        for p in rep["per_type"]:
            assert p["status"] in _TRISTATE
            assert p["status"] not in {"MATCH", "MISSING", "EXTRA", "WRONG_COUNT"}
    # a lone confident side-table + an ambiguous candidate is NOT auto-upgraded to 2.
    rep = fiv.reconcile({"side-table": 2}, [
        _nobj("o1", "side-table", 1.0), _nobj("o2", "dressing-table", 0.5, alts=["side-table"])])
    st = next(p for p in rep["per_type"] if p["type"] == "side-table")
    assert st["confident_detected_count"] == 1 and st["status"] == "UNCERTAIN"


# 13b. partially-invalid response never PASS (via orchestrator; rejected enum object)
def test_partially_invalid_never_pass():
    specs = [_spec("obj_001", "bed", 0.95)]
    enum_bad = json.dumps({"objects": [
        {"object_id": "obj_001", "confidence": 0.9},
        {"object_id": "obj_002", "confidence": 2.0}]})  # invalid -> rejected
    cls = _cls_content([_spec("obj_001", "bed", 0.95)])
    r = fiv.run_inventory_validation(_img(), {"bed": 1}, enabled=True, adjudicate=False,
                                     post=_router(specs, enum_override=enum_bad, cls_override=cls))
    assert r["report"]["rejected_count"] >= 1 and r["overall_status"] != "PASS"


# ══ orchestrator: two-call flow + stages ═════════════════════════════════════

# 16. actual FAL pixels reach the NVIDIA validator (recorded dims/hash)
def test_actual_image_reaches_vlm_with_recorded_pixels():
    sink: dict = {}
    img = _img(80, 60)
    r = fiv.run_inventory_validation(
        img, {"bed": 1}, enabled=True, adjudicate=False,
        post=_router([], enum_override=json.dumps({"objects": []}), sink=sink))
    content = sink["bodies"][0]["messages"][-1]["content"]
    img_part = next(p for p in content if p["type"] == "image_url")
    assert img_part["image_url"]["url"].startswith("data:image/png;base64,")
    import hashlib
    buf = BytesIO(); img.convert("RGB").save(buf, format="PNG")
    assert r["pixels"]["width"] == 80 and r["pixels"]["height"] == 60
    assert r["pixels"]["sha256"] == hashlib.sha256(buf.getvalue()).hexdigest()
    assert r["model"]


def test_two_call_enumerate_then_classify_pass():
    specs = [_spec("obj_001", "bed", 0.95), _spec("obj_002", "side-table", 0.9),
             _spec("obj_003", "side-table", 0.9)]
    r = _run({"bed": 1, "side-table": 2}, specs)
    assert r["vision_calls"] == 2  # enumerate + classify
    assert r["overall_status"] == "PASS"
    assert len(r["objects"]) == 3


# 15. malformed enumeration -> NOT_VALIDATABLE
def test_malformed_enumeration_not_validatable():
    r = fiv.run_inventory_validation(_img(), {"bed": 1}, enabled=True,
                                     post=_router([], enum_override="not json at all"))
    assert r["overall_status"] == "NOT_VALIDATABLE" and r["status"] == "malformed"


def test_json_embedded_in_prose_is_extracted():
    # the model wraps JSON in prose/fences -> still parsed (honest extraction).
    enum = "Here you go:\n```json\n{\"objects\":[{\"object_id\":\"obj_001\",\"confidence\":0.9}]}\n```"
    cls = _cls_content([_spec("obj_001", "bed", 0.95)])
    r = fiv.run_inventory_validation(_img(), {"bed": 1}, enabled=True, adjudicate=False,
                                     post=_router([], enum_override=enum, cls_override=cls))
    assert r["status"] == "ok" and r["overall_status"] == "PASS"


def test_disabled_vision_not_validatable_records_pixels():
    r = fiv.run_inventory_validation(_img(), {"bed": 1}, enabled=False)
    assert r["overall_status"] == "NOT_VALIDATABLE" and r["status"] == "disabled"
    assert r["pixels"]["width"] == 64 and r["pixels"]["sha256"]


# Stage F — focused adjudication resolves an ambiguous candidate
def test_adjudication_resolves_ambiguous_to_confident_then_pass():
    specs = [_spec("obj_001", "side-table", 1.0),
             _spec("obj_002", "dressing-table", 0.5, alts=["side-table"])]
    adj = json.dumps({"objects": [{"object_id": "obj_002", "chosen_type": "side-table",
                                   "alternative_types": [], "confidence": 0.9,
                                   "status": "CONFIDENT", "reason": "matching bedside tables"}]})
    r = _run({"side-table": 2}, specs, adjudicate=True, adj=adj)
    assert r["adjudication_used"] is True and r["vision_calls"] == 3  # enum+classify+adjudicate
    assert _status_of(r["report"], "side-table") == "PASS" and r["overall_status"] == "PASS"


def test_adjudication_unknown_keeps_uncertain():
    specs = [_spec("obj_001", "side-table", 1.0),
             _spec("obj_002", "dressing-table", 0.5, alts=["side-table"])]
    adj = json.dumps({"objects": [{"object_id": "obj_002", "chosen_type": "unknown",
                                   "alternative_types": [], "confidence": 0.3,
                                   "status": "UNKNOWN", "reason": "insufficient evidence"}]})
    r = _run({"side-table": 2}, specs, adjudicate=True, adj=adj)
    assert r["adjudication_used"] is True
    assert _status_of(r["report"], "side-table") == "UNCERTAIN" and r["overall_status"] == "UNCERTAIN"


# ══ error-state observability (no silent swallowing) ═════════════════════════

def _staged_post(specs, *, cls_resp=None, adj_resp=None, enum_override=None):
    def _post(url, body, headers):
        text = body["messages"][-1]["content"][0]["text"]
        if fiv.ADJUDICATION_MARKER in text:
            return adj_resp if adj_resp is not None else _FakeResp(json.dumps({"objects": []}))
        if fiv.CLASSIFICATION_MARKER in text:
            return cls_resp if cls_resp is not None else _FakeResp(_cls_content(specs))
        return _FakeResp(enum_override if enum_override is not None else _enum_content(specs))
    return _post


def test_classification_ok_recorded_on_success():
    r = _run({"bed": 1}, [_spec("obj_001", "bed", 0.95)])
    assert r["classification_status"] == "ok" and r["overall_status"] == "PASS"
    assert r["classification"]["applied"] == 1


def test_classification_provider_error_is_not_validatable():
    specs = [_spec("obj_001", "bed", 0.95)]
    r = fiv.run_inventory_validation(_img(), {"bed": 1}, enabled=True, adjudicate=False,
                                     post=_staged_post(specs, cls_resp=_FakeResp("", status_code=500)))
    assert r["classification_status"] == "provider_error" and r["classification_http"] == 500
    assert r["overall_status"] == "NOT_VALIDATABLE"  # provider failure, never PASS / never fake-ambiguity


def test_classification_malformed_is_not_validatable():
    specs = [_spec("obj_001", "bed", 0.95)]
    r = fiv.run_inventory_validation(_img(), {"bed": 1}, enabled=True, adjudicate=False,
                                     post=_staged_post(specs, cls_resp=_FakeResp("totally not json")))
    assert r["classification_status"] == "malformed"
    assert r["overall_status"] == "NOT_VALIDATABLE"


def test_classification_not_run_when_no_objects():
    r = fiv.run_inventory_validation(_img(), {"bed": 1}, enabled=True, adjudicate=False,
                                     post=_router([], enum_override=json.dumps({"objects": []})))
    assert r["classification_status"] == "not_run"


def test_adjudication_provider_failure_keeps_pre_adjudication_verdict():
    specs = [_spec("obj_001", "side-table", 1.0),
             _spec("obj_002", "dressing-table", 0.5, alts=["side-table"])]
    r = fiv.run_inventory_validation(
        _img(), {"side-table": 2}, enabled=True, adjudicate=True,
        post=_staged_post(specs, adj_resp=_FakeResp("", status_code=503)))
    assert r["adjudication_status"] == "provider_error" and r["adjudication_used"] is True
    assert r["overall_status"] == "UNCERTAIN"  # first verdict kept; a failure never forces PASS


# ══ Step 2 — AI-output position is NOT measurable via this validator ═════════

def test_ai_output_validator_returns_no_positional_coordinates():
    # Step 2 finding: the AI-output inventory path provides NO furniture position
    # (no cx/cy/w/h/bbox) — it classifies identity only. AI-output spatial position is
    # therefore not automatically measurable through this tooling.
    objs = fiv.validate_enumeration({"objects": [{"object_id": "obj_001", "confidence": 0.9}]})["objects"]
    fiv.apply_classification(objs, {"objects": [{"object_id": "obj_001", "type": "bed", "confidence": 0.9}]})
    positional = {"cx", "cy", "x1", "y1", "x2", "y2", "w", "h", "bbox", "bbox_normalized", "position"}
    assert not (positional & set(objs[0].keys())), "AI-output object must carry NO positional fields"


# ══ Step 1 — classification-accuracy regression (Stage B prompt + reconcile) ═

def test_classification_prompt_has_physical_form_and_ambiguity_rules_no_count_leak():
    objs = [{"object_id": "obj_001", "generic_category": "low drawer unit",
             "visual_description": "four drawers, beside bed"}]
    p = fiv.build_classification_prompt(objs)
    assert "REASON FROM PHYSICAL FORM" in p
    assert "AMBIGUITY RULE" in p
    assert "PREFER an ambiguous answer or 'unknown'" in p
    assert fiv.CLASSIFICATION_MARKER in p
    # Stage B is still isolated from expected inventory / counts.
    assert "you are given none" in p
    assert not any(s in p for s in ("side-table = 2", "bed = 1", "expected count", "expected quantity:"))


def test_ambiguous_storage_unit_is_not_a_false_fail():
    # CORRECTED Stage-B behavior for the bedside drawer unit: AMBIGUOUS (dresser OR
    # side-table OR dressing-table), not a confident 'dresser'. It must NOT be a confident
    # extra, so it does not force FAIL; it becomes a candidate for an under-filled type.
    objs = [_nobj("obj_001", "bed", 0.9),
            _nobj("obj_002", "wardrobe", 0.9),
            _nobj("obj_003", "dresser", 0.6, alts=["side-table", "dressing-table"]),
            _nobj("obj_004", "unknown", 0.5)]
    rep = fiv.reconcile({"bed": 1, "side-table": 2, "wardrobe": 1, "dressing-table": 1}, objs)
    assert not any(e["type"] == "dresser" for e in rep["extra_furniture"])
    assert rep["overall_status"] != "FAIL"
    st = next(p for p in rep["per_type"] if p["type"] == "side-table")
    assert st["status"] == "UNCERTAIN" and st["ambiguous_candidate_count"] >= 1


def test_confident_wrong_type_still_fails_reconcile_unchanged():
    # If the model IS genuinely confident about a wrong type, reconcile STILL fails — the
    # reconciliation layer was not weakened to hide confident misclassification.
    rep = fiv.reconcile({"side-table": 2}, [_nobj("obj_003", "dresser", 0.7)])
    assert any(e["type"] == "dresser" for e in rep["extra_furniture"])
    assert rep["overall_status"] == "FAIL"


def test_similar_types_remain_distinguishable():
    assert _status_of(fiv.reconcile({"side-table": 2},
                                    [_nobj("o1", "side-table", 0.9), _nobj("o2", "side-table", 0.9)]),
                      "side-table") == "PASS"
    assert _status_of(fiv.reconcile({"dressing-table": 1}, [_nobj("o1", "dressing-table", 0.9)]),
                      "dressing-table") == "PASS"


# ══ canonical / dynamic / openings ═══════════════════════════════════════════

# 17. canonical furniture remains unchanged
def test_canonical_data_unchanged_by_validation():
    fid, canonical, _label, _items, exp = _discover_plan_room_with_furniture()
    before = copy.deepcopy(canonical["furniture"])
    _run(exp, [_spec("obj_001", "bed", 0.9)])
    after = floor_plan_service.get_canonical(fid)["furniture"]
    assert after == before


# 18. openings excluded
def test_openings_excluded_from_expected():
    items = [{"uid": "a", "item_id": "bed"}, {"uid": "b", "item_id": "door"},
             {"uid": "c", "item_id": "window"}, {"uid": "d", "item_id": "side-table"},
             {"uid": "e", "item_id": "side-table"}]
    exp = fiv.expected_inventory(items)
    assert exp == {"bed": 1, "side-table": 2} and not (set(exp) & fiv.OPENING_ITEM_IDS)


# 19. dynamic inventory remains dynamic
def test_expected_inventory_is_dynamic_from_canonical():
    _fid, _canon, _label, items, exp = _discover_plan_room_with_furniture()
    from collections import Counter
    manual = Counter(f["item_id"] for f in items if f["item_id"] not in fiv.OPENING_ITEM_IDS)
    assert exp == dict(manual) and all(v > 0 for v in exp.values())
