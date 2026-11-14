"""Approach A — version-bound JSON furniture dictionary + detection/synonym rules,
DERIVED from the one authoritative manifest (never a competing inventory).

The dictionary is a serializable, structured view of a room's canonical furniture built
from ``furniture_manifest`` (identity/type/dims/transform/room/version/fingerprint),
enriched with the project's EXISTING authoritative terminology:

  * display names + appearance come from ``furniture_catalog``,
  * detector synonyms are REUSED from ``furniture_object_validation_service._TYPE_SYNONYMS``
    (the same map the output matcher uses — one synonym source, no drift),
  * opening item-ids are REUSED from ``furniture_manifest._OPENING_IDS``.

It adds NO independent inventory extraction and invents NO canonical values. The dynamic
inventory lives in the manifest; the static rules (synonyms, exclusions, preservation
constraints) are code-owned here, so there is no second editable file to disagree. A
companion Markdown *system prompt* (Approach B) is rendered from this same dictionary via a
maintainable template (``app/prompts/furniture_preservation_system.md``).
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from app.data import furniture_catalog
from app.services import furniture_manifest
from app.services.furniture_object_validation_service import _TYPE_SYNONYMS

SCHEMA_VERSION = "mynest.furniture_dictionary/1.0"
DICTIONARY_VERSION = "1.0"
_SUPPORTED_SCHEMAS = {SCHEMA_VERSION}

_OPENING_IDS = furniture_manifest._OPENING_IDS

_PRESERVATION_CONSTRAINTS = [
    "Render every expected furniture item exactly once (respect per-type counts).",
    "Do not add, remove, duplicate, merge, substitute, or invent furniture or decor.",
    "Do not move furniture between rooms; preserve room assignment.",
    "Preserve each item's identity, type, position, dimensions, orientation.",
    "Preserve walls, room boundaries, doors, and windows; invent no openings.",
    "Openings (door/window) are architecture, never counted as furniture.",
    "Improve only materials, textures, lighting, shadows, and finishes.",
]

_TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "prompts" / "furniture_preservation_system.md"


def _dictionary_fingerprint(basis: dict[str, Any]) -> str:
    blob = json.dumps(basis, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def build_dictionary(manifest: dict[str, Any] | None) -> dict[str, Any]:
    """Build the structured, version-bound dictionary for ONE room manifest.

    Pure/offline/deterministic: same manifest → identical dictionary (incl. fingerprint).
    Reuses the manifest's binding, items and counts verbatim; never re-extracts inventory
    and never invents a canonical value. Openings are kept (flagged), not dropped, so the
    categorization is explicit."""
    m = manifest or {}
    items_in = m.get("items") or []
    items: list[dict[str, Any]] = []
    types_present: set[str] = set()
    for e in items_in:
        item_id = str(e.get("item_id") or "")
        is_opening = bool(e.get("is_opening"))
        name, room_type = furniture_catalog.describe(item_id) if item_id else ("", "Other")
        if not is_opening and item_id:
            types_present.add(item_id)
        items.append({
            "uid": e.get("uid"),
            "item_id": item_id,
            "type": item_id,                       # canonical type key (not an instance)
            "name": e.get("name") or name,
            "category": "opening" if is_opening else "furniture",
            "catalog_room_type": room_type,
            "dimensions": {"w": e.get("w"), "h": e.get("h"), "units": m.get("units")},
            "position": {"cx": e.get("cx"), "cy": e.get("cy")},
            "rotation": e.get("rotation"),
            "is_opening": is_opening,
        })
    # synonyms REUSED from the authoritative matcher map, only for the types present
    synonyms = {
        iid: list(_TYPE_SYNONYMS[iid]) for iid in sorted(types_present) if iid in _TYPE_SYNONYMS
    }
    basis = {
        "schema": SCHEMA_VERSION,
        "manifest_fingerprint": m.get("manifest_fingerprint"),
        "design_version_id": m.get("design_version_id"),
        "room_label": m.get("room_label"),
        "items": [[i["uid"], i["item_id"], i["dimensions"]["w"], i["dimensions"]["h"],
                   i["position"]["cx"], i["position"]["cy"], i["rotation"], i["is_opening"]]
                  for i in items],
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "dictionary_version": DICTIONARY_VERSION,
        "manifest_schema_version": m.get("schema_version"),
        "design_version_id": m.get("design_version_id"),
        "room_label": m.get("room_label"),
        "units": m.get("units"),
        "coordinate_system": m.get("coordinate_system"),
        "manifest_fingerprint": m.get("manifest_fingerprint"),
        "expected_furniture_count": m.get("furniture_count", 0),
        "counts": dict(m.get("counts") or {}),
        "items": items,
        "synonyms": synonyms,
        "opening_item_ids": sorted(_OPENING_IDS),
        "preservation_constraints": list(_PRESERVATION_CONSTRAINTS),
        "dictionary_fingerprint": _dictionary_fingerprint(basis),
    }


def validate_dictionary(
    dictionary: dict[str, Any] | None,
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Integrity check (never mutates, never invents). Returns ``{"valid": bool,
    "issues": [codes]}``. Codes: UNSUPPORTED_SCHEMA, DUPLICATE_UID, INVALID_TYPE,
    INVALID_DIMENSIONS, MISSING_UID, MISSING_VERSION, VERSION_MISMATCH,
    FINGERPRINT_MISMATCH, OPENING_MISCATEGORIZED."""
    issues: list[str] = []
    d = dictionary or {}
    if d.get("schema_version") not in _SUPPORTED_SCHEMAS:
        issues.append("UNSUPPORTED_SCHEMA")

    # Defensive: a non-list items collection or a non-dict entry is malformed, not a crash.
    raw_items = d.get("items")
    if not isinstance(raw_items, list):
        issues.append("MALFORMED_ITEMS")
        raw_items = []
    items: list[dict[str, Any]] = []
    for i in raw_items:
        if isinstance(i, dict):
            items.append(i)
        else:
            issues.append("MALFORMED_ITEMS")
    furniture = [i for i in items if not i.get("is_opening")]

    seen: set[str] = set()
    for i in furniture:
        uid = i.get("uid")
        item_id = str(i.get("item_id") or "")
        if not item_id:
            issues.append("INVALID_TYPE")
        if not uid:
            issues.append("MISSING_UID")       # a furniture item without a stable identity
        else:
            if str(uid) in seen:
                issues.append("DUPLICATE_UID")
            seen.add(str(uid))
        dims = i.get("dimensions") or {}
        try:
            w = float(dims.get("w")); h = float(dims.get("h"))
            # NaN/inf must be rejected: `NaN <= 0` is False, so a finiteness check is
            # required or a non-finite dimension would silently pass.
            if not (math.isfinite(w) and math.isfinite(h)) or w <= 0 or h <= 0:
                issues.append("INVALID_DIMENSIONS")
        except (TypeError, ValueError):
            issues.append("INVALID_DIMENSIONS")

    # opening categorization must agree with the authoritative opening set
    for i in items:
        is_open = bool(i.get("is_opening"))
        in_set = str(i.get("item_id") or "") in _OPENING_IDS
        if is_open != in_set:
            issues.append("OPENING_MISCATEGORIZED")
            break

    if not d.get("design_version_id"):
        issues.append("MISSING_VERSION")

    if manifest is not None:
        if d.get("design_version_id") and manifest.get("design_version_id") and \
                str(d["design_version_id"]) != str(manifest["design_version_id"]):
            issues.append("VERSION_MISMATCH")
        if d.get("manifest_fingerprint") != manifest.get("manifest_fingerprint"):
            issues.append("FINGERPRINT_MISMATCH")

    # de-dup while preserving order
    issues = list(dict.fromkeys(issues))
    return {"valid": not issues, "issues": issues}


def normalize_label(label: str | None) -> str | None:
    """Normalize a detector/prompt label to a canonical item_id using the AUTHORITATIVE
    synonym map (reused from the output matcher). Returns the single matching canonical
    type, or ``None`` when the label is unknown OR ambiguous (matches >1 canonical type).

    Never merges two distinct canonical ids and never guesses a furniture instance —
    an ambiguous mapping stays ``None`` (the caller treats it as unresolved)."""
    if not label:
        return None
    q = str(label).lower().strip()
    if not q:
        return None
    matches = {iid for iid, syns in _TYPE_SYNONYMS.items() if any(s in q for s in syns)}
    # an exact canonical item_id / display-name token also resolves (unambiguously)
    if q in furniture_catalog.FURNITURE:
        matches.add(q)
    return next(iter(matches)) if len(matches) == 1 else None


def _render_inventory_lines(dictionary: dict[str, Any]) -> str:
    counts = dictionary.get("counts") or {}
    if not counts:
        return "_(no furniture placed in this room)_"
    return "\n".join(f"- {n}× {name}" for name, n in counts.items())


def _render_opening_lines(dictionary: dict[str, Any]) -> str:
    opens = [i for i in (dictionary.get("items") or []) if i.get("is_opening")]
    if not opens:
        return "_(none)_"
    by: dict[str, int] = {}
    for o in opens:
        by[o["name"]] = by.get(o["name"], 0) + 1
    return "\n".join(f"- {n}× {name}" for name, n in by.items())


def _render_synonym_lines(dictionary: dict[str, Any]) -> str:
    syns = dictionary.get("synonyms") or {}
    if not syns:
        return "_(none applicable)_"
    out = []
    for iid, terms in syns.items():
        name = furniture_catalog.describe(iid)[0]
        out.append(f"- {', '.join(terms)} → {name} (`{iid}`)")
    return "\n".join(out)


_DEFAULT_TEMPLATE = (
    "# SYSTEM — Canonical Furniture Preservation\n\n"
    "Preserve the canonical design exactly; improve only visual presentation.\n\n"
    "Room: {{ROOM_LABEL}}\nDesign version: {{DESIGN_VERSION}}\n"
    "Manifest fingerprint: {{MANIFEST_FINGERPRINT}}\n\n"
    "## EXPECTED FURNITURE\n{{EXPECTED_INVENTORY}}\n\n"
    "## OPENINGS\n{{OPENINGS}}\n\n## RECOGNIZED SYNONYMS\n{{SYNONYMS}}\n"
)


def render_system_prompt(dictionary: dict[str, Any] | None) -> str:
    """Render the Markdown system prompt (Approach B) from the dictionary, filling the
    maintainable template's placeholders with the room's ACTUAL expected inventory.
    Falls back to an embedded template if the file is unavailable (packaging-safe)."""
    d = dictionary or {}
    try:
        template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    except Exception:
        template = _DEFAULT_TEMPLATE
    repl = {
        "{{ROOM_LABEL}}": str(d.get("room_label") or "(unspecified room)"),
        "{{DESIGN_VERSION}}": str(d.get("design_version_id") or "(unbound)"),
        "{{MANIFEST_FINGERPRINT}}": str(d.get("manifest_fingerprint") or "(none)"),
        "{{EXPECTED_INVENTORY}}": _render_inventory_lines(d),
        "{{OPENINGS}}": _render_opening_lines(d),
        "{{SYNONYMS}}": _render_synonym_lines(d),
    }
    out = template
    for k, v in repl.items():
        out = out.replace(k, v)
    # Drop a leading authoring/HTML comment block so the rendered prompt is clean.
    stripped = out.lstrip()
    if stripped.startswith("<!--") and "-->" in stripped:
        out = stripped.split("-->", 1)[1].lstrip()
    # Never emit a misleading prompt with unresolved placeholders: if the template was
    # edited to add a placeholder this renderer does not fill, strip it (and warn) rather
    # than leaking a literal "{{FOO}}" into the prompt/provenance.
    leftovers = re.findall(r"\{\{[A-Z_]+\}\}", out)
    if leftovers:
        logger.warning("system-prompt template had unresolved placeholders: %s", sorted(set(leftovers)))
        out = re.sub(r"\{\{[A-Z_]+\}\}", "", out)
    return out


def build_for_room(manifest: dict[str, Any] | None) -> dict[str, Any]:
    """Convenience: dictionary + its validation + rendered system prompt for one room,
    all from the one manifest. Used by the generation pipeline to persist provenance."""
    dictionary = build_dictionary(manifest)
    validation = validate_dictionary(dictionary, manifest)
    return {
        "furniture_dictionary": dictionary,
        "dictionary_valid": validation["valid"],
        "dictionary_issues": validation["issues"],
        "system_prompt_md": render_system_prompt(dictionary),
    }
