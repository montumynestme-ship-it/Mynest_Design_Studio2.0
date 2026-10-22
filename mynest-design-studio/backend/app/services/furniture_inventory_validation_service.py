"""Post-AI furniture INVENTORY validation (audit stage 8) — evidence-preserving.

Compares the EXPECTED per-type furniture inventory — derived DYNAMICALLY from the
authoritative canonical 2D layout (openings excluded) — against the inventory a
vision LLM DETECTS in the ACTUAL AI-generated (FAL) image pixels.

Multi-stage, evidence-preserving flow (no new model/asset/training; reuses the same
NVIDIA OpenAI-compatible vision infrastructure as ``vision_validation_service``):

  A. ENUMERATE (vision call #1): list EVERY physically distinct furniture object with a
     stable id + a GENERIC description + an existence confidence. NO MyNest vocabulary is
     shown here, so the model describes what it actually sees instead of parroting a type
     list — and taxonomy uncertainty can never make an object disappear.
  B. CLASSIFY (vision call #2): map EXACTLY the enumerated objects (by id) onto the MyNest
     taxonomy — best ``type`` (or "unknown"), plausible ``alternative_types``, and a type
     confidence. The model classifies a FIXED input list, so it cannot invent or drop
     objects and cannot parrot the vocabulary as detections.
  C. EXPECTED inventory — dynamic from canonical, openings excluded (never hardcoded).
  D+E. GLOBAL RECONCILIATION — expected vs enumerated/classified objects, with
     one-physical-object = one-inventory-item accounting. Confident detections count;
     ambiguous objects are candidates that keep a type UNCERTAIN (never forced to PASS,
     never silently dropped). An expected count is NEVER used to pick a classification.
  F. FOCUSED ADJUDICATION (optional vision call) — only when an ambiguous object could
     change the result: re-decide that object neutrally (or say UNKNOWN). Still ambiguous
     -> UNCERTAIN.

Hard rules: the validation TARGET is the AI output pixels (never the PDF / base render);
every model response is UNTRUSTED and passes a STRICT schema validator; malformed /
partially invalid output can NEVER become PASS; ``geometry_faithful`` is never used; this
module NEVER renders, never calls FAL, and never edits geometry/canonical.

Overall status: PASS / FAIL / UNCERTAIN / NOT_VALIDATABLE. Per-type ``status`` is EXACTLY
PASS / FAIL / UNCERTAIN (the fine-grained reason lives in ``classification``).
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any, Callable

from app.data.furniture_catalog import ANNOTATION_IDS, FURNITURE, VISUAL

# Opening primitives in the catalog — excluded from a FURNITURE inventory. Taxonomy
# derived, not plan-specific.
OPENING_ITEM_IDS: frozenset[str] = frozenset({"door", "window"})

_NOTE = "advisory post-AI inventory check — never renders, never edits geometry"
DEFAULT_CONF_THRESHOLD = 0.5
_VALID_CLS_STATUS = {"CONFIDENT", "AMBIGUOUS", "UNKNOWN"}
# Markers so callers/tests can distinguish the three prompt kinds.
CLASSIFICATION_MARKER = "MYNEST TAXONOMY CLASSIFICATION"
ADJUDICATION_MARKER = "FOCUSED FURNITURE RE-CLASSIFICATION"


# ── Taxonomy ─────────────────────────────────────────────────────────────────

def _allowed_types() -> dict[str, dict[str, str]]:
    """MyNest furniture vocabulary (item_id -> display/room/visual), openings excluded.
    Dynamically built from the catalog so new catalog items are covered automatically."""
    out: dict[str, dict[str, str]] = {}
    for iid, (display, room) in FURNITURE.items():
        if iid in OPENING_ITEM_IDS:
            continue
        out[iid] = {"item_id": iid, "display": display, "room": room,
                    "visual": VISUAL.get(iid, "")}
    return out


def _allowed_ids() -> set[str]:
    return set(_allowed_types())


# ── Expected inventory (dynamic, from canonical) ─────────────────────────────

def expected_inventory(furniture_items: list[dict[str, Any]] | None) -> dict[str, int]:
    """Per-type expected counts from a room's canonical furniture, openings excluded.
    No hardcoded counts — purely derived from the supplied canonical items."""
    counts: dict[str, int] = {}
    for f in furniture_items or []:
        iid = str(f.get("item_id") or "").strip()
        if not iid or iid in OPENING_ITEM_IDS or iid in ANNOTATION_IDS:
            continue
        counts[iid] = counts.get(iid, 0) + 1
    return counts


def room_furniture(canonical: dict[str, Any], room_label: str) -> list[dict[str, Any]]:
    """Canonical furniture grouped into the given section label (same grouping the
    render path uses), so expected inventory is scoped per room without plan-specific
    logic. Open-plan combined labels (``A & B``) match either constituent section."""
    from app.services import prompt_service
    norm = prompt_service._normalize_section_name
    want = norm(room_label)
    for label, items in prompt_service.group_by_room(canonical.get("furniture") or []):
        parts = {norm(label)} | {norm(p.strip()) for p in str(label).split("&")}
        if want in parts:
            return list(items)
    return []


# ── Prompts ──────────────────────────────────────────────────────────────────

def build_enumeration_prompt() -> str:
    """Stage A — GENERIC visual enumeration with high recall. No MyNest vocabulary and no
    expected inventory are shown (prevents parroting a type list and prevents hallucinating
    objects to match a count); the model only reports furniture it can actually see. The
    output contract is unchanged (object_id/generic_category/visual_description/confidence),
    so downstream validators and reconciliation are unaffected."""
    schema = ('{"objects": [{"object_id": "obj_001", "generic_category": "...", '
              '"visual_description": "...", "confidence": <0..1>}]}')
    return (
        "Respond with ONLY a single JSON object — no prose, no markdown, no code fences.\n"
        "You are performing STAGE A (visual furniture enumeration) of a multi-stage "
        "pipeline. In Stage A you ONLY enumerate the furniture that is physically visible "
        "in the ACTUAL supplied image. You do NOT assign furniture types, you do NOT use "
        "any furniture catalog, you do NOT decide what is missing or extra, and you do NOT "
        "decide pass/fail/uncertain — afterwards the CODE takes your EXACT object ids, "
        "classifies each against a catalog, and reconciles them against the expected "
        "design. Your ONLY job here is to answer: WHAT FURNITURE OBJECTS CAN I ACTUALLY "
        "SEE? (never: what furniture SHOULD a room like this have).\n"
        "RULES:\n"
        "1. Inspect ONLY the supplied image. Report an object ONLY when it has clear "
        "visible evidence in the pixels. Never invent furniture, never infer it from room "
        "conventions, and never assume a piece exists because rooms usually have one. You "
        "are given NO expected quantities — do not imagine any.\n"
        "2. One PHYSICAL object = exactly ONE entry. Two physically separate objects = TWO "
        "entries with DISTINCT ids, even if they look identical (a side table on EACH side "
        "of a bed is TWO entries). Never merge separate pieces into one entry and never "
        "report a group or a count (no \"two side tables\", no \"side tables x2\").\n"
        "3. Never split ONE physical object into several entries. A single chest or "
        "dressing unit with multiple drawers is still ONE object. Physical-object count is "
        "NOT the same as furniture-type count.\n"
        "4. SCAN TWICE. First do a systematic sweep of the whole image. Then do a SECOND "
        "verification pass hunting specifically for easy-to-miss pieces: furniture on BOTH "
        "sides of beds / sofas / desks, items beside or around wardrobes, pieces in room "
        "corners and along wall edges, small furniture, partially occluded furniture, and "
        "multiple visually-similar pieces (make sure EACH separate one gets its own entry).\n"
        "5. Ignore walls, doors, windows, curtains, floors, ceilings, rugs, plants, vases, "
        "wall art, lamps, and any décor or architectural element.\n"
        "6. Give each object a stable id obj_001, obj_002, ... in top-left-to-bottom-right "
        "order; ids denote PHYSICAL objects, not types. For each object provide a short "
        "plain-English 'generic_category' describing its shape (e.g. \"bed\", \"tall "
        "cabinet\", \"low drawer unit\", \"desk\", \"chair\"), a brief 'visual_description' "
        "(position / colour / distinctive features), and 'confidence' in [0,1] that it is a "
        "real distinct furniture object you can actually see.\n"
        "Output JSON exactly: " + schema
    )


def build_classification_prompt(objects: list[dict[str, Any]]) -> str:
    """Stage B — classify the FIXED enumerated list onto the MyNest taxonomy. The model
    may not add or remove objects; it classifies exactly these object_ids."""
    vocab = [{"type": iid, "name": a["display"], "looks_like": a["visual"]}
             for iid, a in _allowed_types().items()]
    items = [{"object_id": o["object_id"], "generic_category": o.get("generic_category", ""),
              "visual_description": o.get("visual_description", "")} for o in objects]
    schema = ('{"objects": [{"object_id": "...", "type": "<allowed type id or \'unknown\'>", '
              '"alternative_types": ["..."], "confidence": <0..1>}]}')
    return (
        "Respond with ONLY a single JSON object — no prose, no markdown, no code fences.\n"
        + CLASSIFICATION_MARKER + " (Stage B). Your task: WHAT MYNEST TYPE BEST DESCRIBES "
        "EACH ALREADY-DETECTED OBJECT? The objects below were enumerated from the image in "
        "Stage A; classify each onto the allowed MyNest furniture type ids using its "
        "generic_category and visual_description as evidence. For EACH listed object_id put "
        "the single best-matching allowed id in 'type' (or 'unknown' if none is sufficiently "
        "supported), and ANY other genuinely plausible allowed ids in 'alternative_types' "
        "(empty list only when exactly one type clearly fits). Give 'confidence' in [0,1] "
        "for the chosen type.\n"
        "REASON FROM PHYSICAL FORM, not just the wording of generic_category/visual_"
        "description. Weigh the observable features: overall size, whether the piece is TALL "
        "(vertical, wardrobe/cabinet-like) or LOW, its width, number of drawers, number of "
        "doors, open shelves vs closed storage, a flat tabletop, legs vs a solid base, a "
        "mirror, and its placement (beside a bed, in a dressing area, at a desk, or against "
        "a wall).\n"
        "AMBIGUITY RULE (important): report an object as CONFIDENT — a single 'type' with an "
        "EMPTY 'alternative_types' — ONLY when the visible features clearly single out exactly "
        "ONE allowed type. When the SAME visible evidence plausibly fits two or more allowed "
        "types — which is common for low bedroom storage pieces (e.g. side-table vs dresser vs "
        "dressing-table vs console, which can all be low units with drawers) — you MUST list "
        "every plausible one (best guess in 'type', the rest in 'alternative_types') and lower "
        "'confidence' accordingly, so the object is treated as ambiguous. If no allowed type is "
        "well supported by the visible features, use 'unknown'. PREFER an ambiguous answer or "
        "'unknown' over a confident but uncertain type — NEVER report a single confident type "
        "for a visually ambiguous object.\n"
        "CRITICAL: classify EXACTLY these object_ids and nothing else — do NOT add, remove, "
        "split, or merge objects; do NOT invent any new object or object_id; do NOT return "
        "an object_id that is not in this list; and NEVER choose a type to satisfy any "
        "expected quantity (you are given none). Objects: " + json.dumps(items) +
        ". Output JSON exactly: " + schema +
        ". Allowed types (id, name, looks_like): " + json.dumps(vocab)
    )


def build_adjudication_prompt(ambiguous: list[dict[str, Any]]) -> str:
    """Stage F — focused re-decision of specific ambiguous objects, neutrally. Never
    reveals expected counts; explicitly allows UNKNOWN."""
    items = [{"object_id": o.get("object_id"),
              "visual_description": o.get("visual_description", ""),
              "generic_category": o.get("generic_category", ""),
              "candidate_types": sorted({o.get("type")} | set(o.get("alternative_types") or []))}
             for o in ambiguous]
    schema = ('{"objects": [{"object_id": "...", "chosen_type": "<allowed type id or '
              '\'unknown\'>", "alternative_types": ["..."], "confidence": <0..1>, '
              '"status": "CONFIDENT|AMBIGUOUS|UNKNOWN", "reason": "..."}]}')
    return (
        "Respond with ONLY a single JSON object — no prose, no markdown, no code fences.\n"
        + ADJUDICATION_MARKER + " (Stage F). Your task: CAN THIS SPECIFIC ALREADY-DETECTED "
        "AMBIGUOUS OBJECT BE CLASSIFIED WITH SUFFICIENT VISUAL EVIDENCE? Inspect the ACTUAL "
        "image again and re-decide ONLY the listed objects, using ONLY each object's "
        "supplied candidate_types (or 'unknown'). For each, choose the candidate the visible "
        "object is most consistent with and briefly justify it in 'reason' from the pixels. "
        "Do NOT force a result — if the image does not give enough evidence, return status "
        "UNKNOWN. Do NOT create a new object or object_id, do NOT return any object_id not "
        "listed, do NOT change any object that is not listed, and do NOT use any expected "
        "quantity (you are given none). Objects to re-classify: " + json.dumps(items) +
        ". Output JSON exactly: " + schema
    )


# ── Strict response validators (the untrusted boundary) ──────────────────────

def _coerce_json(raw: Any) -> Any:
    """Parse a model response into a Python object. Accepts an already-decoded object,
    strict JSON, a ```json fenced block, or a JSON object embedded in surrounding prose
    (extracts the first balanced ``{...}``). Returns None when no JSON object is present.
    Only EXTRACTS the model's own structured output — never fabricates content."""
    if not isinstance(raw, str):
        return raw
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1] if s.count("```") >= 2 else s.strip("`")
        if s.lstrip().lower().startswith("json"):
            s = s.lstrip()[4:]
        s = s.strip()
    try:
        return json.loads(s)
    except (ValueError, TypeError):
        pass
    start = s.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(s[start:i + 1])
                except (ValueError, TypeError):
                    return None
    return None


def validate_enumeration(raw: Any) -> dict[str, Any]:
    """Validate the Stage-A enumeration response -> ``{status, objects:[...], rejected}``.
    Each object needs a non-empty unique ``object_id`` and a numeric ``confidence`` in
    [0,1]; generic_category/visual_description are optional. Malformed top-level JSON ->
    status 'malformed'. No taxonomy here (that is Stage B)."""
    rejected: list[dict[str, Any]] = []
    raw = _coerce_json(raw)
    if raw is None:
        return {"status": "malformed", "objects": [],
                "rejected": [{"reason": "not valid JSON", "item": None}]}
    if not isinstance(raw, dict) or not isinstance(raw.get("objects"), list):
        return {"status": "malformed", "objects": [],
                "rejected": [{"reason": "'objects' missing or not a list", "item": None}]}

    objects: list[dict[str, Any]] = []
    seen: set[str] = set()
    for it in raw["objects"]:
        if not isinstance(it, dict):
            rejected.append({"reason": "object is not a JSON object", "item": it})
            continue
        oid = str(it.get("object_id") or "").strip()
        if not oid:
            rejected.append({"reason": "missing object_id", "item": it})
            continue
        if oid in seen:
            rejected.append({"reason": "duplicate object_id", "item": it})
            continue
        conf = it.get("confidence")
        if isinstance(conf, bool) or not isinstance(conf, (int, float)) or not (0.0 <= float(conf) <= 1.0):
            rejected.append({"reason": "invalid confidence", "item": it})
            continue
        seen.add(oid)
        objects.append({
            "object_id": oid,
            "generic_category": str(it.get("generic_category") or ""),
            "visual_description": str(it.get("visual_description") or ""),
            "enum_confidence": round(float(conf), 4),
            # classification placeholders until Stage B (object is never lost)
            "type": "unknown", "raw_type": "", "alternative_types": [],
            "confidence": 0.0, "classification_status": "UNKNOWN",
        })

    status = "ok" if (objects or not rejected) else "empty"
    return {"status": status, "objects": objects, "rejected": rejected}


def apply_classification(objects: list[dict[str, Any]], raw: Any) -> dict[str, Any]:
    """Merge the Stage-B classification response into the enumerated objects (by id).
    Only known object_ids are accepted (the model cannot invent objects); an enumerated
    object left unclassified stays ``unknown``. A non-taxonomy type is coerced to
    ``unknown`` (never guessed). Returns ``{applied, ignored}`` counts."""
    allowed = _allowed_ids()
    by_id = {o["object_id"]: o for o in objects}
    raw = _coerce_json(raw)
    applied = 0
    ignored: list[dict[str, Any]] = []
    if isinstance(raw, dict) and isinstance(raw.get("objects"), list):
        for it in raw["objects"]:
            if not isinstance(it, dict):
                ignored.append({"reason": "not an object", "item": it})
                continue
            oid = str(it.get("object_id") or "").strip()
            if oid not in by_id:
                ignored.append({"reason": "unknown object_id", "item": it})
                continue
            conf = it.get("confidence")
            if isinstance(conf, bool) or not isinstance(conf, (int, float)) or not (0.0 <= float(conf) <= 1.0):
                ignored.append({"reason": "invalid confidence", "item": it})
                continue
            raw_type = str(it.get("type") or "").strip()
            typ = raw_type if raw_type in allowed else "unknown"
            alts = [str(a) for a in (it.get("alternative_types") or []) if str(a) in allowed]
            alts = [a for a in dict.fromkeys(alts) if a != typ]
            cls = "UNKNOWN" if typ == "unknown" else ("AMBIGUOUS" if alts else "CONFIDENT")
            by_id[oid].update({
                "type": typ, "raw_type": raw_type, "alternative_types": alts,
                "confidence": round(float(conf), 4), "classification_status": cls,
            })
            applied += 1
    return {"applied": applied, "ignored": ignored}


def validate_adjudication(raw: Any) -> dict[str, dict[str, Any]]:
    """Validate the focused re-classification response -> {object_id: decision}. Invalid
    decisions are dropped (the object stays as it was). Never raises."""
    allowed = _allowed_ids()
    out: dict[str, dict[str, Any]] = {}
    raw = _coerce_json(raw)
    if not isinstance(raw, dict) or not isinstance(raw.get("objects"), list):
        return out
    for it in raw["objects"]:
        if not isinstance(it, dict):
            continue
        oid = str(it.get("object_id") or "").strip()
        if not oid:
            continue
        conf = it.get("confidence")
        if isinstance(conf, bool) or not isinstance(conf, (int, float)) or not (0.0 <= float(conf) <= 1.0):
            continue
        chosen = str(it.get("chosen_type") or "").strip()
        typ = chosen if chosen in allowed else "unknown"
        alts = [str(a) for a in (it.get("alternative_types") or []) if str(a) in allowed and str(a) != typ]
        cls = "UNKNOWN" if typ == "unknown" else ("AMBIGUOUS" if alts else "CONFIDENT")
        out[oid] = {"type": typ, "alternative_types": alts, "confidence": round(float(conf), 4),
                    "classification_status": cls, "reason": str(it.get("reason") or "")[:300]}
    return out


# ── Stage D+E: global reconciliation ─────────────────────────────────────────

def _candidate_types(o: dict[str, Any]) -> set[str]:
    if o["type"] == "unknown":
        return set()
    return {o["type"]} | set(o.get("alternative_types") or [])


def _is_confident(o: dict[str, Any], thr: float) -> bool:
    return (o["classification_status"] == "CONFIDENT" and o["type"] != "unknown"
            and not o.get("alternative_types") and o["confidence"] >= thr)


def reconcile(
    expected: dict[str, int],
    objects: list[dict[str, Any]],
    *,
    conf_threshold: float = DEFAULT_CONF_THRESHOLD,
    rejected: list[Any] | int = 0,
) -> dict[str, Any]:
    """Global expected-vs-detected reconciliation (one physical object = one inventory
    item). Confident objects count toward a type; ambiguous objects are *candidates* that
    keep a type UNCERTAIN; unknown/low-confidence objects never satisfy an expected type.
    Per-type ``status`` is the tri-state contract (PASS/FAIL/UNCERTAIN)."""
    expected = {k: int(v) for k, v in (expected or {}).items() if v > 0}
    confident = [o for o in objects if _is_confident(o, conf_threshold)]
    unknown = [o for o in objects if o["type"] == "unknown"]
    ambiguous = [o for o in objects if o not in confident and o not in unknown]

    confident_by_type = Counter(o["type"] for o in confident)
    conf_val: dict[str, float] = {}
    for o in confident:
        conf_val[o["type"]] = min(conf_val.get(o["type"], 1.0), o["confidence"])

    amb_candidate_types: set[str] = set()
    for o in ambiguous:
        amb_candidate_types |= _candidate_types(o)

    per_type: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    extra: list[dict[str, Any]] = []
    for t in sorted(set(expected) | set(confident_by_type) | amb_candidate_types):
        e = expected.get(t, 0)
        c = confident_by_type.get(t, 0)
        amb = [o for o in ambiguous if t in _candidate_types(o)]
        possible = c + len(amb)
        if e == 0:
            if c > 0:
                classification, status = "EXTRA", "FAIL"
                extra.append({"type": t, "expected": 0, "detected": c, "delta": c})
            else:
                classification, status = "AMBIGUOUS_EXTRA", "UNCERTAIN"
        elif c == e:
            classification, status = "MATCH", "PASS"
        elif c > e:
            classification, status = "WRONG_COUNT", "FAIL"
            extra.append({"type": t, "expected": e, "detected": c, "delta": c - e})
        else:  # c < e — under-detection, never FAIL
            classification = "AMBIGUOUS" if amb else "MISSING"
            status = "UNCERTAIN"
            missing.append({"type": t, "expected": e, "confident": c,
                            "ambiguous_candidates": len(amb), "possible": possible})
        per_type.append({
            "type": t, "expected_count": e, "confident_detected_count": c,
            "ambiguous_candidate_count": len(amb), "possible_count": possible,
            "count_delta": c - e, "confidence": conf_val.get(t),
            "status": status, "classification": classification,
        })

    rejected_count = rejected if isinstance(rejected, int) else len(rejected or [])
    unmatched_objects = [{"object_id": o["object_id"], "raw_type": o["raw_type"],
                          "generic_category": o.get("generic_category", ""),
                          "visual_description": o["visual_description"],
                          "confidence": o["confidence"]} for o in unknown]
    ambiguous_objects = [{"object_id": o["object_id"], "type": o["type"],
                          "alternative_types": o["alternative_types"],
                          "generic_category": o.get("generic_category", ""),
                          "visual_description": o["visual_description"],
                          "confidence": o["confidence"]} for o in ambiguous]

    if extra:
        overall = "FAIL"
    elif missing or ambiguous_objects or unmatched_objects or rejected_count:
        overall = "UNCERTAIN"
    else:
        overall = "PASS"

    return {
        "overall_status": overall,
        "conf_threshold": conf_threshold,
        "per_type": per_type,
        "missing_furniture": missing,
        "extra_furniture": extra,
        "unmatched_objects": unmatched_objects,
        "ambiguous_objects": ambiguous_objects,
        "rejected_count": rejected_count,
        "enumerated_total": len(objects),
        "confident_total": len(confident),
        "expected_total": sum(expected.values()),
    }


def _resolvable_ambiguous(expected: dict[str, int], report: dict[str, Any]) -> list[str]:
    """object_ids of ambiguous objects whose resolution could change an UNCERTAIN type
    that is under-filled (worth a focused second look)."""
    under = {p["type"] for p in report["per_type"]
             if p["status"] == "UNCERTAIN" and p["expected_count"] > p["confident_detected_count"]}
    out: list[str] = []
    for a in report["ambiguous_objects"]:
        if ({a["type"]} | set(a["alternative_types"])) & under:
            out.append(a["object_id"])
    return out


# ── Orchestrator: send ACTUAL AI pixels to the NVIDIA vision LLM ─────────────

def _image_dims_and_hash(image: Any) -> tuple[bytes, int, int, str]:
    from io import BytesIO

    from PIL import Image
    if isinstance(image, bytes):
        raw = image
        pil = Image.open(BytesIO(raw))
    else:
        pil = image
        buf = BytesIO()
        image.convert("RGB").save(buf, format="PNG")
        raw = buf.getvalue()
    w, h = pil.size
    return raw, int(w), int(h), hashlib.sha256(raw).hexdigest()


def _result(status: str, **extra: Any) -> dict[str, Any]:
    base = {"status": status, "note": _NOTE, "overall_status": "NOT_VALIDATABLE",
            "pixels": None, "model": None, "report": None}
    base.update(extra)
    return base


def _post_vision(url, body, headers, post):
    if post is not None:
        return post(url, body, headers)
    import httpx
    with httpx.Client(timeout=httpx.Timeout(90.0, connect=10.0)) as c:
        return c.post(url, json=body, headers=headers)


def run_inventory_validation(
    image: Any,
    expected: dict[str, int],
    *,
    conf_threshold: float = DEFAULT_CONF_THRESHOLD,
    enabled: bool | None = None,
    adjudicate: bool = True,
    post: Callable[[str, dict[str, Any], dict[str, str]], Any] | None = None,
) -> dict[str, Any]:
    """Multi-stage inventory validation against the ACTUAL AI image. NEVER fabricates a
    result and NEVER coerces errors/ambiguity to PASS. Records image dims/hash + model."""
    from app.core.config import (
        NVIDIA_API_KEY,
        NVIDIA_VISION_BASE,
        NVIDIA_VISION_ENABLED,
        NVIDIA_VISION_MODEL,
    )
    from app.services.vision_validation_service import _image_data_uri

    raw_png, width, height, sha = _image_dims_and_hash(image)
    pixels = {"width": width, "height": height, "sha256": sha, "sha256_8": sha[:8],
              "bytes": len(raw_png)}
    use_enabled = NVIDIA_VISION_ENABLED if enabled is None else bool(enabled)
    if not use_enabled:
        return _result("disabled", pixels=pixels, model=NVIDIA_VISION_MODEL,
                       reason="NVIDIA_VISION_ENABLED is false")
    if not NVIDIA_API_KEY:
        return _result("unconfigured", pixels=pixels, model=NVIDIA_VISION_MODEL,
                       reason="NVIDIA_API_KEY is not set")

    headers = {"Authorization": f"Bearer {NVIDIA_API_KEY}", "Accept": "application/json"}
    url = f"{NVIDIA_VISION_BASE.rstrip('/')}/chat/completions"
    data_uri = _image_data_uri(raw_png)
    calls = {"n": 0}

    def _call(prompt_text: str):
        calls["n"] += 1
        body = {"model": NVIDIA_VISION_MODEL, "messages": [
            {"role": "system", "content": "You respond with only a single raw JSON "
             "object matching the requested schema. Never include prose, explanation, "
             "markdown, or code fences."},
            {"role": "user", "content": [
                {"type": "text", "text": prompt_text},
                {"type": "image_url", "image_url": {"url": data_uri}}]}],
            "temperature": 0.0, "max_tokens": 1500,
            "response_format": {"type": "json_object"}}
        return _post_vision(url, body, headers, post)

    def _content_or(resp):
        if getattr(resp, "status_code", None) != 200:
            return None, getattr(resp, "status_code", None)
        try:
            return resp.json()["choices"][0]["message"]["content"], 200
        except (ValueError, KeyError, IndexError, TypeError):
            return None, 200

    # Stage A — enumerate
    try:
        respA = _call(build_enumeration_prompt())
    except Exception as exc:  # noqa: BLE001
        return _result("error", pixels=pixels, model=NVIDIA_VISION_MODEL,
                       reason=f"transport: {type(exc).__name__}", vision_calls=calls["n"])
    contentA, code = _content_or(respA)
    if code != 200:
        return _result("provider_error", pixels=pixels, model=NVIDIA_VISION_MODEL,
                       http_status=code, reason=f"HTTP {code}", vision_calls=calls["n"])
    if contentA is None:
        return _result("malformed", pixels=pixels, model=NVIDIA_VISION_MODEL,
                       http_status=200, reason="unsupported response shape", vision_calls=calls["n"])
    enum = validate_enumeration(contentA)
    if enum["status"] == "malformed":
        return _result("malformed", pixels=pixels, model=NVIDIA_VISION_MODEL,
                       http_status=200, enumeration=enum,
                       reason="enumeration response was not parseable JSON", vision_calls=calls["n"])

    objects = enum["objects"]
    classification = {"applied": 0, "ignored": []}
    classification_status = "not_run"          # not_run|ok|provider_error|transport_error|malformed
    classification_http: int | None = None
    classification_error: str | None = None
    # Stage B — classify the enumerated objects (only if any were enumerated). Failures are
    # recorded EXPLICITLY (never silently swallowed) so a provider/transport/parse failure
    # is never mistaken for genuine visual ambiguity.
    if objects:
        try:
            respB = _call(build_classification_prompt(objects))
            classification_http = getattr(respB, "status_code", None)
            if classification_http != 200:
                classification_status = "provider_error"
            else:
                contentB, _ = _content_or(respB)
                if contentB is None or _coerce_json(contentB) is None:
                    classification_status = "malformed"
                else:
                    classification = apply_classification(objects, contentB)
                    classification_status = "ok"
        except Exception as exc:  # noqa: BLE001 — recorded, not hidden
            classification_status = "transport_error"
            classification_error = type(exc).__name__

    report = reconcile(expected, objects, conf_threshold=conf_threshold, rejected=enum["rejected"])

    # Stage F — focused adjudication only when it could change the result. Failures are
    # recorded EXPLICITLY and leave the pre-adjudication verdict untouched (never a PASS).
    adjudication_used = False
    adjudication_status = "not_needed"         # not_needed|ok|provider_error|transport_error|malformed
    adjudication_http: int | None = None
    adjudication_error: str | None = None
    to_adjudicate = _resolvable_ambiguous(expected, report) if adjudicate else []
    if to_adjudicate:
        amb_objs = [o for o in objects if o["object_id"] in to_adjudicate]
        adjudication_used = True
        try:
            respC = _call(build_adjudication_prompt(amb_objs))
            adjudication_http = getattr(respC, "status_code", None)
            if adjudication_http != 200:
                adjudication_status = "provider_error"
            else:
                contentC, _ = _content_or(respC)
                if contentC is None or _coerce_json(contentC) is None:
                    adjudication_status = "malformed"
                else:
                    decisions = validate_adjudication(contentC)
                    by_id = {o["object_id"]: o for o in objects}
                    for oid, dec in decisions.items():
                        if oid in by_id:
                            by_id[oid].update({
                                "type": dec["type"], "alternative_types": dec["alternative_types"],
                                "confidence": dec["confidence"],
                                "classification_status": dec["classification_status"],
                                "adjudicated": True, "adjudication_reason": dec["reason"],
                            })
                    report = reconcile(expected, objects, conf_threshold=conf_threshold,
                                       rejected=enum["rejected"])
                    adjudication_status = "ok"
        except Exception as exc:  # noqa: BLE001 — recorded, not hidden
            adjudication_status = "transport_error"
            adjudication_error = type(exc).__name__

    # A classification provider/transport/malformed failure on enumerated objects means we
    # could NOT actually classify what Stage A saw. That is a MODEL/PROVIDER failure, NOT
    # genuine visual ambiguity — surface it as NOT_VALIDATABLE (and thus never PASS) rather
    # than letting the all-"unknown" objects read as an honest ambiguous result.
    overall = report["overall_status"]
    if objects and classification_status in {"provider_error", "transport_error", "malformed"}:
        overall = "NOT_VALIDATABLE"

    return {
        "status": "ok",
        "note": _NOTE,
        "overall_status": overall,
        "expected": dict({k: v for k, v in expected.items() if v > 0}),
        "pixels": pixels,
        "model": NVIDIA_VISION_MODEL,
        "http_status": 200,
        "vision_calls": calls["n"],
        "classification_status": classification_status,
        "classification_http": classification_http,
        "classification_error": classification_error,
        "classification": classification,
        "adjudication_used": adjudication_used,
        "adjudication_status": adjudication_status,
        "adjudication_http": adjudication_http,
        "adjudication_error": adjudication_error,
        "enumeration": enum,
        "objects": objects,
        "report": report,
    }
