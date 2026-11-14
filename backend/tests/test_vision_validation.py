"""Vision-LLM semantic validation (audit stage 7).

Tests the deterministic validator/sanitizer that guards UNTRUSTED vision-model
output: schema validation, malformed/unsupported responses, hallucinated (unknown)
entity ids, attempted geometry injection, confidence coercion, and the opt-in
adapter's safe disabled behaviour. No network / no model is exercised.
"""

from app.services import vision_validation_service as vv

_EXTRACTION = {
    "text": [{"id": "t1", "text": "Kitchen"}],
    "walls": [{"id": "H0"}],
    "openings": [{"id": "door_001", "kind": "door", "status": "VALID"}],
    "furniture": [{"id": "cand_0", "class_name": "bed", "status": "CANDIDATE"}],
    "rooms": [{"id": "living-area", "label": "Living Area", "status": "CONFIRMED"}],
}


def _known():
    return vv.collect_known_ids(_EXTRACTION)


# ── Known-id collection ──────────────────────────────────────────────────────

def test_collect_known_ids():
    k = _known()
    assert k["text"] == {"t1"}
    assert k["walls"] == {"H0"}
    assert k["openings"] == {"door_001"}
    assert k["furniture"] == {"cand_0"}
    assert k["rooms"] == {"living-area"}


# ── Valid response ───────────────────────────────────────────────────────────

def test_valid_response_kept_and_id_referenced():
    resp = {
        "room_semantics": [{"room_id": "living-area", "label": "Living Area",
                            "confidence": "high", "reason": "sofa + tv wall"}],
        "furniture_classifications": [{"candidate_id": "cand_0", "suggested_class": "bed",
                                       "confidence": "medium", "reason": "rectangular"}],
        "opening_validations": [{"opening_id": "door_001", "kind": "door", "valid": True,
                                 "reason": "swing arc"}],
        "relationships": [{"subject_id": "cand_0", "object_id": "door_001",
                           "relation": "near", "reason": "adjacent"}],
        "uncertain": [{"entity_id": "H0", "reason": "faint line"}],
    }
    out = vv.validate_vision_response(resp, _known())
    assert out["status"] == "ok"
    assert out["stats"]["kept"] == 5 and out["stats"]["rejected"] == 0
    assert out["validated"]["room_semantics"][0]["room_id"] == "living-area"
    assert out["validated"]["relationships"][0]["subject_id"] == "cand_0"


# ── Hallucinated / unknown ids ───────────────────────────────────────────────

def test_unknown_id_rejected():
    resp = {"room_semantics": [{"room_id": "ghost-room", "label": "X", "confidence": "high"}]}
    out = vv.validate_vision_response(resp, _known())
    assert out["validated"]["room_semantics"] == []
    assert out["stats"]["rejected"] == 1
    assert "not a known entity id" in out["rejected"][0]["reason"]


def test_relationship_requires_both_ids_known():
    resp = {"relationships": [{"subject_id": "cand_0", "object_id": "ghost", "relation": "near"}]}
    out = vv.validate_vision_response(resp, _known())
    assert out["validated"]["relationships"] == []
    assert out["stats"]["rejected"] == 1


def test_contradiction_all_ids_must_be_known():
    good = {"contradictions": [{"entity_ids": ["cand_0", "door_001"], "issue": "x"}]}
    bad = {"contradictions": [{"entity_ids": ["cand_0", "ghost"], "issue": "x"}]}
    assert len(vv.validate_vision_response(good, _known())["validated"]["contradictions"]) == 1
    assert vv.validate_vision_response(bad, _known())["validated"]["contradictions"] == []


# ── Geometry injection is blocked ────────────────────────────────────────────

def test_geometry_injection_rejected():
    for bad_item in (
        {"candidate_id": "cand_0", "suggested_class": "bed", "cx": 100, "cy": 50},
        {"candidate_id": "cand_0", "suggested_class": "bed", "bbox": [0, 0, 1, 1]},
        {"candidate_id": "cand_0", "suggested_class": "bed", "rotation": 90},
    ):
        out = vv.validate_vision_response({"furniture_classifications": [bad_item]}, _known())
        assert out["validated"]["furniture_classifications"] == []
        assert "forbidden geometry" in out["rejected"][0]["reason"]


def test_validated_output_contains_no_geometry_keys():
    resp = {"room_semantics": [{"room_id": "living-area", "label": "Living Area",
                                "confidence": "high", "reason": "ok"}]}
    out = vv.validate_vision_response(resp, _known())
    item = out["validated"]["room_semantics"][0]
    assert not (set(item) & vv._FORBIDDEN_KEYS)


# ── Malformed / unsupported responses ────────────────────────────────────────

def test_malformed_json_string():
    out = vv.validate_vision_response("{ not valid json", _known())
    assert out["status"] == "malformed"
    assert out["stats"]["kept"] == 0


def test_non_object_response_is_malformed():
    for raw in ([1, 2, 3], "42", "\"a string\""):
        out = vv.validate_vision_response(raw, _known())
        assert out["status"] == "malformed"


def test_non_dict_items_rejected_not_crash():
    resp = {"room_semantics": ["not-an-object", 123, None]}
    out = vv.validate_vision_response(resp, _known())
    assert out["validated"]["room_semantics"] == []
    assert out["stats"]["rejected"] == 3


def test_valid_json_string_is_parsed():
    import json
    resp = json.dumps({"uncertain": [{"entity_id": "H0", "reason": "faint"}]})
    out = vv.validate_vision_response(resp, _known())
    assert out["validated"]["uncertain"][0]["entity_id"] == "H0"


# ── Coercion: unknown stays uncertain/unknown ────────────────────────────────

def test_unsupported_confidence_coerced_to_uncertain():
    resp = {"room_semantics": [{"room_id": "living-area", "label": "Living Area",
                                "confidence": "banana"}]}
    out = vv.validate_vision_response(resp, _known())
    assert out["validated"]["room_semantics"][0]["confidence"] == "uncertain"


def test_missing_label_becomes_unknown():
    resp = {"room_semantics": [{"room_id": "living-area", "confidence": "low"}]}
    out = vv.validate_vision_response(resp, _known())
    assert out["validated"]["room_semantics"][0]["label"] == "UNKNOWN"


# ── Adapter safety (opt-in) ──────────────────────────────────────────────────

def test_run_vision_validation_disabled_by_default():
    # NVIDIA_VISION_ENABLED defaults False → no network, honest disabled status.
    out = vv.run_vision_validation(b"", _EXTRACTION)
    assert out["status"] in ("disabled", "unconfigured")
    assert out["stats"]["kept"] == 0


def test_note_states_advisory_only():
    out = vv.validate_vision_response({}, _known())
    assert "never overrides deterministic geometry" in out["note"]
