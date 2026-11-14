"""Phase 1 — advisory OUTPUT-image furniture assessment (evidence-based, never definitive).

Consumes version-bound deterministic BASE-RENDER furniture boxes (frontend screen-space,
in the capture frame) + the generated AI image, runs the EXISTING output validators
(``furniture_object_validation_service`` + a detector), and reports advisory candidates for
MISSING / EXTRA / changed furniture. It is deliberately ADVISORY:

  * identity comes ONLY from the deterministic base registry (uid/item_id), never the detector;
  * it NEVER downloads model weights — the detector must be supplied EXPLICITLY by the caller
    (``detector=None`` → NOT_VALIDATABLE), so production stays dormant until a detector is
    enabled + calibrated;
  * detector/image unavailable, no evidence, or a detector exception → NOT_VALIDATABLE
    (never a PASS, never ``FAITHFUL``);
  * it never mutates canonical/scene data and never assigns a definitive fidelity status.
"""
from __future__ import annotations

import math
import os
from typing import Any, Callable

from app.services.furniture_object_validation_service import build_object_registry, validate_objects

_REQUIRED_BOX_KEYS = ("uid", "item_id", "x", "y", "width", "height")

# Opening item_ids (architecture, not furniture) — excluded from a FURNITURE
# inventory comparison. Kept in sync with ``furniture_manifest._OPENING_IDS``.
_OPENING_ITEM_IDS = {"window", "bay-window-seat", "door"}

MATCH = "MATCH"
MISMATCH = "MISMATCH"
AMBIGUOUS = "AMBIGUOUS"
NOT_ASSESSABLE = "NOT_ASSESSABLE"


def reconcile_with_manifest(
    base_boxes: list[dict[str, Any]] | None,
    manifest: dict[str, Any] | None,
) -> dict[str, Any]:
    """Confirm the deterministic base-render evidence describes the SAME furniture
    inventory as the authoritative manifest, so an OUTPUT assessment built on these
    boxes is provably assessed against *that* manifest (spec §E), not a stale or
    unrelated set.

    Compares FURNITURE only (openings excluded) by stable ``uid`` when both sides carry
    uids, else falls back to a per-``item_id`` count comparison. Pure, offline, advisory:

      * ``MATCH``          — the evidence's furniture set equals the manifest's.
      * ``MISMATCH``       — the evidence is missing or adds furniture vs the manifest
                             (so the two are not the same inventory; the boxes must not
                             be trusted as evidence for this manifest's output).
      * ``NOT_ASSESSABLE`` — no manifest or no evidence to compare.
    """
    man_items = [e for e in (manifest or {}).get("items") or [] if not e.get("is_opening")]
    box_furn = [b for b in (base_boxes or []) if str(b.get("item_id")) not in _OPENING_ITEM_IDS]
    if not man_items or not box_furn:
        return {"status": NOT_ASSESSABLE,
                "reason": "no manifest furniture or no base furniture evidence to reconcile"}

    # Duplicate stable identity on EITHER side makes a uid comparison unsound and the
    # count fallback can then paper over a real substitution (two items sharing a uid vs
    # two genuinely different items). Reject as AMBIGUOUS rather than returning a false
    # MATCH (spec: "reject ambiguous or duplicate stable identities").
    man_uid_list = [str(e["uid"]) for e in man_items if e.get("uid")]
    box_uid_list = [str(b["uid"]) for b in box_furn if b.get("uid")]
    dup_man = len(set(man_uid_list)) != len(man_uid_list)
    dup_box = len(set(box_uid_list)) != len(box_uid_list)
    if dup_man or dup_box:
        return {"status": AMBIGUOUS, "basis": "uid",
                "duplicate_manifest_uid": dup_man, "duplicate_evidence_uid": dup_box,
                "reason": "duplicate stable uid(s) in the manifest or base-render evidence; "
                          "identity is ambiguous, so an inventory match cannot be asserted"}

    man_uids = set(man_uid_list)
    box_uids = set(box_uid_list)
    # Prefer a stable-uid comparison; only when BOTH sides fully carry (unique) uids is it exact.
    if len(man_uids) == len(man_items) and len(box_uids) == len(box_furn):
        missing = sorted(man_uids - box_uids)   # expected by manifest, absent from evidence
        extra = sorted(box_uids - man_uids)     # in evidence, not in the manifest
        if not missing and not extra:
            return {"status": MATCH, "basis": "uid", "furniture_count": len(man_uids)}
        return {"status": MISMATCH, "basis": "uid",
                "missing_uids": missing, "extra_uids": extra,
                "reason": "base-render furniture evidence does not match the manifest's "
                          "expected furniture (by stable uid)"}

    # Fallback: compare counts per item_id (openings already excluded).
    def _counts(rows: list[dict[str, Any]]) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in rows:
            k = str(r.get("item_id"))
            out[k] = out.get(k, 0) + 1
        return out

    man_counts, box_counts = _counts(man_items), _counts(box_furn)
    if man_counts == box_counts:
        return {"status": MATCH, "basis": "item_id_counts",
                "furniture_count": sum(man_counts.values())}
    return {"status": MISMATCH, "basis": "item_id_counts",
            "manifest_counts": man_counts, "evidence_counts": box_counts,
            "reason": "base-render furniture evidence does not match the manifest's "
                      "expected furniture (by item_id count)"}


def validate_base_box_evidence(
    room_boxes: Any,
    *,
    expected_version_id: str | None = None,
    declared_version_id: str | None = None,
) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Validate client-supplied base-render furniture boxes for ONE room/base render.

    Returns ``(clean_boxes, None)`` when usable, else ``(None, reason)``. Rejects a
    version mismatch (boxes from a different base render/version than the generation
    snapshot), malformed/incomplete boxes, non-finite or non-positive sizes, and duplicate
    uids — so evidence from different base renders is never mixed and malformed evidence
    never enters the assessment.
    """
    # Version binding: when the caller asserts an expected version (the production
    # contract always does — the generation snapshot id), the evidence MUST declare its
    # version and it MUST match. A missing declared version is rejected (not silently
    # accepted as unbound), so evidence from an unknown base render can never enter the
    # assessment. With no expected version (legacy/non-production), the check is skipped.
    if expected_version_id:
        if not declared_version_id:
            return None, "MISSING_DECLARED_VERSION"
        if str(expected_version_id) != str(declared_version_id):
            return None, "VERSION_MISMATCH"
    if not isinstance(room_boxes, list) or not room_boxes:
        return None, "NO_BOXES"
    clean: list[dict[str, Any]] = []
    seen: set[str] = set()
    for b in room_boxes:
        if not isinstance(b, dict) or any(k not in b for k in _REQUIRED_BOX_KEYS):
            return None, "MALFORMED_BOX"
        try:
            w = float(b["width"]); h = float(b["height"])
            x = float(b["x"]); y = float(b["y"])
        except (TypeError, ValueError):
            return None, "MALFORMED_BOX"
        if not (math.isfinite(w) and math.isfinite(h) and math.isfinite(x) and math.isfinite(y)):
            return None, "MALFORMED_BOX"
        if w <= 0 or h <= 0:
            return None, "NON_POSITIVE_BOX"
        uid = str(b["uid"])
        if uid in seen:
            return None, "DUPLICATE_UID"
        seen.add(uid)
        clean.append(b)
    return clean, None


def assess_output_inventory(
    base_boxes: list[dict[str, Any]] | None,
    ai_image: Any | None,
    *,
    detector: Callable[[Any], list[dict[str, Any]]] | None,
    image_width: int = 1216,
    image_height: int = 832,
    output_width: int | None = None,
    output_height: int | None = None,
) -> dict[str, Any]:
    """Advisory output-inventory assessment for one room. ``detector`` MUST be supplied to
    run (no implicit weight download); otherwise NOT_VALIDATABLE. The base registry is built
    in the CAPTURE frame (``image_width``/``image_height``); the detector runs on the AI
    output. When the output dimensions are known and DIFFER from the capture frame, the two
    are not in the same coordinate space, so correspondence cannot be established without a
    validated projection — we return NOT_VALIDATABLE rather than silently scaling (an edit
    render re-composes the scene, so a naive resize would distort matching). Returns the
    existing ``validate_objects`` report wrapped as ``advisory=True`` and
    ``calibration_status='NOT_CALIBRATED'`` — NEVER a definitive fidelity verdict and never
    sets ``geometry_status=FAITHFUL``."""
    try:
        iw = int(image_width)
        ih = int(image_height)
    except (TypeError, ValueError):
        return {"overall_status": "NOT_VALIDATABLE", "advisory": True,
                "calibration_status": "NOT_CALIBRATED",
                "reason": "invalid base capture dimensions"}
    if iw <= 0 or ih <= 0:
        return {"overall_status": "NOT_VALIDATABLE", "advisory": True,
                "calibration_status": "NOT_CALIBRATED",
                "reason": f"base capture dimensions must be positive, got {iw}x{ih}"}

    if not base_boxes:
        return {"overall_status": "NOT_VALIDATABLE", "advisory": True,
                "calibration_status": "NOT_CALIBRATED",
                "reason": "no deterministic base furniture evidence for this room"}
    # Defense in depth (do not trust the caller): malformed/duplicate/non-positive base
    # boxes can never enter the assessment, regardless of entry point. Version binding is
    # the caller's responsibility (it holds the expected version), so it is NOT re-checked
    # here — only structural validity.
    _clean, _why = validate_base_box_evidence(base_boxes)
    if _clean is None:
        return {"overall_status": "NOT_VALIDATABLE", "advisory": True,
                "calibration_status": "NOT_CALIBRATED",
                "reason": f"malformed base furniture evidence: {_why}"}
    base_boxes = _clean
    if ai_image is None:
        return {"overall_status": "NOT_VALIDATABLE", "advisory": True,
                "calibration_status": "NOT_CALIBRATED",
                "reason": "no AI output image available"}

    # Resolve output dimensions from the image object if not explicitly provided
    if output_width is None or output_height is None:
        try:
            from PIL import Image as _PILImage
            if isinstance(ai_image, _PILImage.Image):
                output_width, output_height = ai_image.size
            elif isinstance(ai_image, (bytes, bytearray)):
                import io
                with _PILImage.open(io.BytesIO(bytes(ai_image))) as _im:
                    output_width, output_height = _im.size
            elif isinstance(ai_image, str) and os.path.exists(ai_image):
                with _PILImage.open(ai_image) as _im:
                    output_width, output_height = _im.size
        except Exception:
            pass

    if output_width is not None and output_height is not None:
        try:
            ow = int(output_width)
            oh = int(output_height)
            if ow <= 0 or oh <= 0:
                return {"overall_status": "NOT_VALIDATABLE", "advisory": True,
                        "calibration_status": "NOT_CALIBRATED",
                        "reason": f"invalid output dimensions: {ow}x{oh}"}
            if (ow, oh) != (iw, ih):
                return {"overall_status": "NOT_VALIDATABLE", "advisory": True,
                        "calibration_status": "NOT_CALIBRATED",
                        "reason": f"output dimensions {ow}x{oh} differ from the base "
                                  f"capture frame {iw}x{ih}; object correspondence is "
                                  "not established without a validated projection"}
        except (TypeError, ValueError):
            return {"overall_status": "NOT_VALIDATABLE", "advisory": True,
                    "calibration_status": "NOT_CALIBRATED",
                    "reason": f"invalid output dimensions: {output_width}x{output_height}"}

    if detector is None:
        return {"overall_status": "NOT_VALIDATABLE", "advisory": True,
                "calibration_status": "NOT_CALIBRATED",
                "reason": "no output detector configured (advisory-only until a detector is "
                          "enabled and calibrated)"}
    # Split openings from furniture so the FURNITURE comparison is furniture-only (the same
    # exclusion the manifest reconciliation uses), and so a door/window box is never matched
    # as a piece of furniture (which would fabricate a missing/extra furniture candidate).
    # Openings go to the registry's opening slot (validated separately, where wall
    # association stays NOT_VALIDATABLE) — architectural-preservation evidence is kept, not
    # weakened.
    furniture_boxes = [b for b in base_boxes if str(b.get("item_id")) not in _OPENING_ITEM_IDS]
    opening_boxes = [b for b in base_boxes if str(b.get("item_id")) in _OPENING_ITEM_IDS]
    if not furniture_boxes:
        return {"overall_status": "NOT_VALIDATABLE", "advisory": True,
                "calibration_status": "NOT_CALIBRATED",
                "reason": "base evidence has no furniture (openings only) to assess"}
    registry = build_object_registry(furniture_boxes, opening_boxes, image_width=iw, image_height=ih)
    try:
        ai_boxes = detector(ai_image)
    except Exception as exc:  # noqa: BLE001 — detector unavailable → not validatable, never PASS
        return {"overall_status": "NOT_VALIDATABLE", "advisory": True,
                "calibration_status": "NOT_CALIBRATED",
                "reason": f"detector unavailable: {type(exc).__name__}"}
    report = validate_objects(registry, ai_boxes)
    # Equal output/base dimensions are necessary but NOT sufficient for comparability: they
    # do not establish that the AI render shares the base's camera/projection, so any
    # placement/ordering signal below is advisory, not a verified physical-placement claim.
    return {**report, "advisory": True, "calibration_status": "NOT_CALIBRATED",
            "camera_comparability": "UNVERIFIED"}
