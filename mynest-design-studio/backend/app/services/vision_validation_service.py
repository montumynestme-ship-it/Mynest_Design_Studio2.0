"""Vision-LLM SEMANTIC validation stage (audit stage 7).

A configured NVIDIA Vision LLM reasons over the DETERMINISTIC CV/OCR results and
returns semantic judgements only — it NEVER generates or edits geometry. Its raw
output is UNTRUSTED and is passed through a strict deterministic validator before
anything is surfaced:

- Return value is structured JSON only.
- Every conclusion MUST reference an existing detected entity ID; conclusions that
  reference unknown IDs are rejected.
- Any coordinate/geometry field the model tries to emit is rejected (the model may
  not invent/move/resize/rotate objects or create/delete walls/furniture, and may
  not override deterministic geometry).
- Unknown/ambiguous is coerced to UNCERTAIN.
- Uses the configured NVIDIA Vision model only (OpenAI-compatible chat endpoint).
  No FLUX / no image generation. The LLM call is opt-in (NVIDIA_VISION_ENABLED);
  the deterministic validator works without any network.
"""

from __future__ import annotations

import json
from typing import Any

_NOTE = "advisory semantic validation only — never overrides deterministic geometry"

# Geometry/coordinate keys the vision model is NEVER allowed to emit on a
# conclusion. Presence of any → the item is rejected (attempted geometry injection).
_FORBIDDEN_KEYS: frozenset[str] = frozenset({
    "x", "y", "z", "cx", "cy", "x1", "y1", "x2", "y2", "w", "h", "width", "height",
    "bbox", "bbox_normalized", "rotation", "rotation_deg", "angle", "polygon",
    "points", "coordinate", "coordinates", "position", "footprint", "boundary",
})

_CONF_LEVELS = frozenset({"high", "medium", "low", "uncertain"})


# ── Known-ID collection ──────────────────────────────────────────────────────

def collect_known_ids(extraction: dict[str, Any]) -> dict[str, set[str]]:
    """Gather the entity IDs the model is allowed to reference, by kind.

    ``extraction`` is the composed deterministic result with optional keys:
    ``text`` (OCR), ``walls``, ``openings``, ``furniture`` (candidates), ``rooms``.
    """
    def _ids(items: Any, *keys: str) -> set[str]:
        out: set[str] = set()
        for it in items or []:
            if not isinstance(it, dict):
                continue
            for k in keys:
                v = it.get(k)
                if v is not None:
                    out.add(str(v))
                    break
        return out

    text = extraction.get("text") or extraction.get("ocr") or []
    return {
        "text": _ids(text, "id"),
        "walls": _ids(extraction.get("walls"), "id"),
        "openings": _ids(extraction.get("openings"), "id"),
        "furniture": _ids(extraction.get("furniture") or extraction.get("candidates"),
                          "id", "uid"),
        "rooms": _ids(extraction.get("rooms"), "id", "room_id"),
    }


def _all_ids(known: dict[str, set[str]]) -> set[str]:
    out: set[str] = set()
    for s in known.values():
        out |= s
    return out


# ── Deterministic response validator (the security boundary) ─────────────────

def _has_forbidden(item: dict[str, Any]) -> bool:
    return any(k in _FORBIDDEN_KEYS for k in item)


def _norm_conf(v: Any) -> str:
    s = str(v).strip().lower() if v is not None else "uncertain"
    return s if s in _CONF_LEVELS else "uncertain"


def validate_vision_response(
    raw: Any, known: dict[str, set[str]]
) -> dict[str, Any]:
    """Validate + sanitize an UNTRUSTED vision-model response against the known
    entity IDs. Returns ``{status, validated:{...}, rejected:[...], stats:{...}}``.
    Never raises on bad input — malformed/unsupported responses yield status
    ``malformed`` with empty ``validated``."""
    rejected: list[dict[str, Any]] = []

    def reject(section: str, item: Any, reason: str) -> None:
        rejected.append({"section": section, "reason": reason, "item": item})

    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return _result("malformed", _empty(), [{"section": "*", "reason": "not valid JSON",
                                                     "item": None}])
    if not isinstance(raw, dict):
        return _result("malformed", _empty(),
                       [{"section": "*", "reason": "response is not a JSON object", "item": raw}])

    all_ids = _all_ids(known)
    validated = _empty()

    def _keep_single(section: str, id_key: str, id_pool: set[str],
                     extra: dict[str, Any]) -> None:
        for it in raw.get(section) or []:
            if not isinstance(it, dict):
                reject(section, it, "item is not an object")
                continue
            if _has_forbidden(it):
                reject(section, it, "contains forbidden geometry/coordinate field")
                continue
            ent = it.get(id_key)
            if ent is None or str(ent) not in id_pool:
                reject(section, it, f"{id_key} not a known entity id")
                continue
            clean: dict[str, Any] = {id_key: str(ent)}
            for k, coerce in extra.items():
                clean[k] = coerce(it.get(k))
            validated[section].append(clean)

    _keep_single("room_semantics", "room_id", known["rooms"], {
        "label": lambda v: str(v) if v else "UNKNOWN",
        "confidence": _norm_conf,
        "reason": lambda v: str(v)[:400] if v else "",
    })
    _keep_single("label_validations", "text_id", known["text"], {
        "agrees": lambda v: bool(v) if isinstance(v, bool) else None,
        "suggested_label": lambda v: str(v) if v else None,
        "confidence": _norm_conf,
        "reason": lambda v: str(v)[:400] if v else "",
    })
    _keep_single("furniture_classifications", "candidate_id", known["furniture"], {
        "suggested_class": lambda v: str(v) if v else "UNKNOWN",
        "confidence": _norm_conf,
        "reason": lambda v: str(v)[:400] if v else "",
    })
    _keep_single("opening_validations", "opening_id", known["openings"], {
        "kind": lambda v: str(v).lower() if str(v).lower() in ("door", "window") else "uncertain",
        "valid": lambda v: bool(v) if isinstance(v, bool) else None,
        "reason": lambda v: str(v)[:400] if v else "",
    })
    _keep_single("uncertain", "entity_id", all_ids, {
        "reason": lambda v: str(v)[:400] if v else "",
    })

    # relationships: subject_id + object_id must BOTH be known
    for it in raw.get("relationships") or []:
        if not isinstance(it, dict):
            reject("relationships", it, "item is not an object")
            continue
        if _has_forbidden(it):
            reject("relationships", it, "contains forbidden geometry/coordinate field")
            continue
        s, o = it.get("subject_id"), it.get("object_id")
        if s is None or o is None or str(s) not in all_ids or str(o) not in all_ids:
            reject("relationships", it, "subject_id/object_id not both known")
            continue
        validated["relationships"].append({
            "subject_id": str(s), "object_id": str(o),
            "relation": str(it.get("relation") or "related_to"),
            "reason": str(it.get("reason") or "")[:400],
        })

    # contradictions: entity_ids list, ALL must be known
    for it in raw.get("contradictions") or []:
        if not isinstance(it, dict):
            reject("contradictions", it, "item is not an object")
            continue
        if _has_forbidden(it):
            reject("contradictions", it, "contains forbidden geometry/coordinate field")
            continue
        ents = it.get("entity_ids")
        if not isinstance(ents, list) or not ents or any(str(e) not in all_ids for e in ents):
            reject("contradictions", it, "entity_ids missing or references unknown id")
            continue
        validated["contradictions"].append({
            "entity_ids": [str(e) for e in ents],
            "issue": str(it.get("issue") or "")[:200],
            "reason": str(it.get("reason") or "")[:400],
        })

    kept = sum(len(v) for v in validated.values())
    status = "ok" if kept or not rejected else "empty"
    return _result(status, validated, rejected)


def _empty() -> dict[str, list]:
    return {"room_semantics": [], "label_validations": [], "furniture_classifications": [],
            "opening_validations": [], "relationships": [], "contradictions": [],
            "uncertain": []}


def _result(status: str, validated: dict[str, list], rejected: list) -> dict[str, Any]:
    return {
        "status": status,
        "note": _NOTE,
        "validated": validated,
        "rejected": rejected,
        "stats": {
            "kept": sum(len(v) for v in validated.values()),
            "rejected": len(rejected),
            **{k: len(v) for k, v in validated.items()},
        },
    }


# ── Prompt builder ───────────────────────────────────────────────────────────

def build_prompt(extraction: dict[str, Any]) -> str:
    """Build the strict, ID-referenced instruction for the vision model. The model
    is told to return JSON only, reference existing IDs, and never emit geometry."""
    known = collect_known_ids(extraction)
    context = {
        "text": extraction.get("text") or extraction.get("ocr") or [],
        "walls": [{"id": w.get("id")} for w in (extraction.get("walls") or [])
                  if isinstance(w, dict)],
        "openings": [{k: o.get(k) for k in ("id", "kind", "status")}
                     for o in (extraction.get("openings") or []) if isinstance(o, dict)],
        "furniture": [{k: f.get(k) for k in ("id", "uid", "class_name", "item_id", "status")}
                      for f in (extraction.get("furniture") or extraction.get("candidates") or [])
                      if isinstance(f, dict)],
        "rooms": [{k: r.get(k) for k in ("id", "room_id", "label", "status")}
                  for r in (extraction.get("rooms") or []) if isinstance(r, dict)],
    }
    return (
        "You are a floor-plan SEMANTIC validator. Reason ONLY about meaning; you must "
        "NOT produce or change any geometry. Rules: return a SINGLE JSON object only; "
        "every conclusion must reference an existing entity id from the context; never "
        "output coordinates, sizes, rotations, bboxes or polygons; never invent, move, "
        "resize, rotate, add or delete walls/furniture/openings; if unsure, mark it "
        "uncertain. Valid ids: " + json.dumps({k: sorted(v) for k, v in known.items()}) +
        ". JSON schema keys: room_semantics[{room_id,label,confidence,reason}], "
        "label_validations[{text_id,agrees,suggested_label,confidence,reason}], "
        "furniture_classifications[{candidate_id,suggested_class,confidence,reason}], "
        "opening_validations[{opening_id,kind,valid,reason}], "
        "relationships[{subject_id,object_id,relation,reason}], "
        "contradictions[{entity_ids,issue,reason}], uncertain[{entity_id,reason}]. "
        "Context: " + json.dumps(context)
    )


# ── NVIDIA Vision LLM adapter (opt-in; never fabricates) ─────────────────────

def _image_data_uri(image: Any) -> str:
    import base64
    from io import BytesIO
    if isinstance(image, bytes):
        raw = image
    else:  # PIL image
        buf = BytesIO()
        image.convert("RGB").save(buf, format="PNG")
        raw = buf.getvalue()
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


def run_vision_validation(image: Any, extraction: dict[str, Any]) -> dict[str, Any]:
    """Full stage 7: call the configured NVIDIA Vision model and return the
    VALIDATED semantic layer. Opt-in via NVIDIA_VISION_ENABLED; returns a clear
    non-ok status (never fabricates) when disabled/unconfigured/erroring."""
    from app.core.config import (
        NVIDIA_API_KEY,
        NVIDIA_VISION_BASE,
        NVIDIA_VISION_ENABLED,
        NVIDIA_VISION_MODEL,
    )
    known = collect_known_ids(extraction)
    if not NVIDIA_VISION_ENABLED:
        return _result("disabled", _empty(), [])
    if not NVIDIA_API_KEY:
        return _result("unconfigured", _empty(), [])

    import httpx
    prompt = build_prompt(extraction)
    body = {
        "model": NVIDIA_VISION_MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": _image_data_uri(image)}},
        ]}],
        "temperature": 0.0,
        "max_tokens": 1500,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {NVIDIA_API_KEY}", "Accept": "application/json"}
    try:
        with httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0)) as c:
            resp = c.post(f"{NVIDIA_VISION_BASE.rstrip('/')}/chat/completions",
                          json=body, headers=headers)
    except httpx.HTTPError as exc:
        return _result("error", _empty(), [{"section": "*", "reason": f"transport: {exc}",
                                            "item": None}])
    if resp.status_code != 200:
        return _result("provider_error", _empty(),
                       [{"section": "*", "reason": f"HTTP {resp.status_code}", "item": None}])
    try:
        content = resp.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        return _result("malformed", _empty(),
                       [{"section": "*", "reason": "unsupported response shape", "item": None}])
    return validate_vision_response(content, known)
