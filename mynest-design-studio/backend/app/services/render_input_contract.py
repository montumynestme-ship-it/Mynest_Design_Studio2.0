"""Render-input contract validator (Phase 2I, strengthened in Phase 2J).

Read-only consistency + provenance check over the deterministic render inputs — the
immutable canonical furniture, the live scene (room grouping + opening placements),
and optional base-render / render-attempt metadata. It NEVER changes canonical data,
geometry, rooms, walls, openings, camera, or the render; it only reports, with honest
PASS / FAIL / UNCERTAIN, whether the inputs are complete, self-consistent, and
provably correlated to one render attempt.

Phase 2J strengthens:
- furniture IDENTITY (scene item_id must match the canonical record for a uid),
- opening status validated AGAINST the existing wall-verification evidence
  (missing/unknown status never silently becomes PLACED; a status that contradicts
  `verified`/`wall_id` is an INCONSISTENT violation),
- render-attempt PROVENANCE (base PNG sha/dims recorded; design-version correlation;
  optional actual-bytes hash match; unverifiable correlation reports UNCERTAIN).

No new source of truth: it consumes `scene_service.build_scene` and
`floor_plan_service` canonical. `validate_render_input(...)` is pure/unit-testable.
This validates render INPUTS and PROVENANCE only — NOT AI-output furniture preservation.
"""

from __future__ import annotations

import hashlib
from typing import Any

_VALID_OPENING_STATUS = {"PLACED", "NEEDS_REVIEW"}


def _is_opening(item_id: str) -> bool:
    """Openings are architecture, validated as doors/windows — same rule the scene
    builder uses (`'door'`/`'window'` substring; this also covers `bay-window-seat`)."""
    s = (item_id or "").lower()
    return "door" in s or "window" in s


def _classify_opening(p: dict[str, Any]) -> str:
    """Classify one placement against its wall-verification evidence.

    PLACED        explicit PLACED and consistent with verified+wall_id
    NEEDS_REVIEW  explicit NEEDS_REVIEW and consistent with (not verified / no wall)
    INCONSISTENT  explicit status contradicts the verified/wall_id evidence
    UNKNOWN       status missing or not a recognized value (never treated as PLACED)
    """
    st = p.get("status")
    verified = p.get("verified") is True
    has_wall = bool(p.get("wall_id"))
    evidence_placed = verified and has_wall
    if st not in _VALID_OPENING_STATUS:
        return "UNKNOWN"
    expected = "PLACED" if evidence_placed else "NEEDS_REVIEW"
    if st != expected:
        return "INCONSISTENT"
    return st


def validate_render_input(
    scene: dict[str, Any],
    canonical: dict[str, Any],
    base_meta: dict[str, Any] | None = None,
    base_image_sha256: str | None = None,
    attempt_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Pure consistency + provenance check.

    scene: a `build_scene` result. canonical: the design version's ``{"furniture": [...]}``.
    base_meta: persisted base-render metadata (sha256/width/height/design_version_id).
    base_image_sha256: the ACTUAL sha-256 of the base PNG bytes the caller hashed, for
      file-level correlation (never fabricated; omit when the file is unavailable).
    attempt_meta: render-attempt metadata (generation_id/design_version_id/geometry_hash).
    """
    rooms = scene.get("rooms", []) or []
    all_canon = canonical.get("furniture", []) or []
    canon_furn = [f for f in all_canon if not _is_opening(str(f.get("item_id", "")))]
    canon_open = [f for f in all_canon if _is_opening(str(f.get("item_id", "")))]
    canon_item_by_uid = {str(f.get("uid", "")): str(f.get("item_id", "")) for f in canon_furn}

    # --- furniture: scene uid -> room ids + scene item_id(s) --------------------
    uid_rooms: dict[str, list[str]] = {}
    uid_scene_items: dict[str, set[str]] = {}
    scene_furn_uids: set[str] = set()
    for r in rooms:
        rid = str(r.get("id", ""))
        for f in r.get("furniture", []) or []:
            if _is_opening(str(f.get("item_id", ""))):
                continue
            u = str(f.get("uid", ""))
            scene_furn_uids.add(u)
            uid_rooms.setdefault(u, []).append(rid)
            uid_scene_items.setdefault(u, set()).add(str(f.get("item_id", "")))

    canon_uids = set(canon_item_by_uid)
    per_uid: list[dict[str, Any]] = []
    missing: list[str] = []
    duplicated: list[str] = []
    identity_mismatches: list[dict[str, Any]] = []
    for u, citem in canon_item_by_uid.items():
        rs = uid_rooms.get(u, [])
        sitems = uid_scene_items.get(u, set())
        id_ok = (not sitems) or sitems == {citem}
        if not id_ok:
            identity_mismatches.append({"uid": u, "canonical_item_id": citem, "scene_item_ids": sorted(sitems)})
        if len(rs) == 0:
            status = "FAIL"; missing.append(u)
        elif len(rs) > 1:
            status = "FAIL"; duplicated.append(u)
        elif not id_ok:
            status = "FAIL"
        else:
            status = "PASS"
        per_uid.append({"uid": u, "item_id": citem, "scene_item_ids": sorted(sitems), "rooms": rs, "status": status})
    unexpected = sorted(scene_furn_uids - canon_uids)
    furniture_ok = not missing and not duplicated and not unexpected and not identity_mismatches

    # --- rooms: unique/non-empty ids, duplicate labels, overlap -----------------
    ids = [str(r.get("id", "")) for r in rooms]
    labels = [str(r.get("label", "")) for r in rooms]
    empty_room_ids = [i for i in range(len(ids)) if not ids[i].strip()]
    duplicate_room_ids = sorted({i for i in ids if ids.count(i) > 1})
    duplicate_room_labels = sorted({l for l in labels if labels.count(l) > 1})
    overlapping_furniture = sorted(u for u, rs in uid_rooms.items() if len(rs) > 1)
    rooms_ok = not duplicate_room_ids and not empty_room_ids and not overlapping_furniture

    # --- openings: status validated against verification evidence ---------------
    counts = {"PLACED": 0, "NEEDS_REVIEW": 0, "INCONSISTENT": 0, "UNKNOWN": 0}
    per_opening: list[dict[str, Any]] = []
    for r in rooms:
        rid = str(r.get("id", ""))
        for p in r.get("opening_placements", []) or []:
            cls = _classify_opening(p)
            counts[cls] += 1
            per_opening.append({
                "id": p.get("id"), "kind": p.get("kind"), "room_id": rid,
                "source": p.get("source"), "wall_id": p.get("wall_id"),
                "verified": p.get("verified"), "declared_status": p.get("status"),
                "classification": cls,
            })
    openings_ok = counts["INCONSISTENT"] == 0 and counts["UNKNOWN"] == 0 and counts["NEEDS_REVIEW"] == 0

    # --- render-attempt provenance ----------------------------------------------
    scene_dvid = scene.get("design_version_id")
    base_correlation: dict[str, Any] | None = None
    provenance = "NOT_EVALUATED"  # only graded when provenance metadata is supplied
    if base_meta is not None or attempt_meta is not None:
        bm = base_meta or {}
        am = attempt_meta or {}
        base_sha = bm.get("sha256") or bm.get("base_png_sha256")
        base_dvid = bm.get("design_version_id")
        attempt_dvid = am.get("design_version_id")
        # design-version correlation: any provided dvid must equal the scene's
        dvids = [d for d in (base_dvid, attempt_dvid) if d is not None]
        version_match = bool(dvids) and all(d == scene_dvid for d in dvids)
        # actual-bytes correlation (only when the caller hashed the real file)
        if base_image_sha256 is not None and base_sha is not None:
            file_match: bool | None = (base_image_sha256 == base_sha)
        else:
            file_match = None
        base_correlation = {
            "base_sha256": base_sha,
            "base_actual_sha256": base_image_sha256,
            "base_width": bm.get("width"),
            "base_height": bm.get("height"),
            "scene_design_version_id": scene_dvid,
            "base_design_version_id": base_dvid,
            "attempt_design_version_id": attempt_dvid,
            "generation_id": am.get("generation_id"),
            "geometry_hash": am.get("geometry_hash"),
            "version_match": version_match,
            "file_match": file_match,
            "has_base_image_hash": base_sha is not None,
        }
        if (not version_match) or (file_match is False):
            provenance = "FAIL"
        elif version_match and file_match is True:
            provenance = "PASS"
        else:
            # version matches but the base IMAGE bytes could not be proven
            # (e.g. production records geometry_hash/prompt_hash but no base PNG sha).
            provenance = "UNCERTAIN"

    # --- honest overall status --------------------------------------------------
    reasons: list[str] = []
    if missing:
        reasons.append(f"{len(missing)} canonical furniture uid(s) missing from scene")
    if duplicated or overlapping_furniture:
        reasons.append("furniture assigned to multiple rooms")
    if unexpected:
        reasons.append(f"{len(unexpected)} unexpected scene furniture uid(s)")
    if identity_mismatches:
        reasons.append(f"{len(identity_mismatches)} furniture identity mismatch(es)")
    if duplicate_room_ids:
        reasons.append("duplicate room ids")
    if empty_room_ids:
        reasons.append("empty room id(s)")
    if counts["INCONSISTENT"]:
        reasons.append(f"{counts['INCONSISTENT']} opening status inconsistent with wall evidence")
    if provenance == "FAIL":
        reasons.append("base/attempt provenance correlation failed")

    if reasons:
        overall = "FAIL"
    else:
        soft: list[str] = []
        if counts["NEEDS_REVIEW"]:
            soft.append(f"{counts['NEEDS_REVIEW']} opening(s) NEEDS_REVIEW")
        if counts["UNKNOWN"]:
            soft.append(f"{counts['UNKNOWN']} opening(s) with UNKNOWN status")
        if provenance == "UNCERTAIN":
            soft.append("base-image provenance not provable (no verified base sha)")
        if soft:
            overall = "UNCERTAIN"
            reasons = soft
        else:
            overall = "PASS"

    return {
        "floor_plan_id": scene.get("floor_plan_id"),
        "design_version_id": scene_dvid,
        "overall_status": overall,
        "reasons": reasons,
        "scope_note": "validates render INPUTS + PROVENANCE only; NOT AI-output furniture preservation",
        "furniture": {
            "canonical_count": len(canon_furn),
            "scene_count": len(scene_furn_uids),
            "missing_uids": sorted(missing),
            "duplicated_uids": sorted(duplicated),
            "unexpected_uids": unexpected,
            "identity_mismatches": identity_mismatches,
            "overall": "PASS" if furniture_ok else "FAIL",
            "per_uid": per_uid,
        },
        "rooms": {
            "count": len(rooms),
            "ids": ids,
            "unique_ids": len(ids) == len(set(ids)),
            "empty_id_indices": empty_room_ids,
            "duplicate_room_ids": duplicate_room_ids,
            "duplicate_room_labels": duplicate_room_labels,
            "overlapping_furniture_uids": overlapping_furniture,
            "overall": "PASS" if rooms_ok else "FAIL",
        },
        "openings": {
            "canonical_count": len(canon_open),
            "placement_count": sum(counts.values()),
            "placed": counts["PLACED"],
            "needs_review": counts["NEEDS_REVIEW"],
            "inconsistent": counts["INCONSISTENT"],
            "unknown": counts["UNKNOWN"],
            "overall": "PASS" if openings_ok else ("FAIL" if counts["INCONSISTENT"] else "UNCERTAIN"),
            "per_opening": per_opening,
        },
        "provenance": provenance,
        "base_correlation": base_correlation,
    }


def validate_file(
    file_id: str,
    base_meta: dict[str, Any] | None = None,
    base_image_path: str | None = None,
    attempt_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Thin wrapper: build the live scene + load the current canonical, then validate.
    If `base_image_path` is given, the ACTUAL base bytes are hashed for file-level
    correlation (never a stale/unrelated file — the caller supplies the real path).
    Read-only; no changes and no FAL calls."""
    from app.services import floor_plan_service, scene_service

    scene = scene_service.build_scene(file_id)
    canonical: dict[str, Any] = {"furniture": []}
    info = floor_plan_service.get_latest_version_info(file_id)
    if info is not None:
        # Inject the current authoritative design_version_id exactly as the /scene API
        # route does (floor_plans.py), so provenance correlation sees the same value.
        scene.setdefault("design_version_id", info[0])
        canonical = floor_plan_service.get_version_canonical(info[0]) or {"furniture": []}
    base_sha: str | None = None
    if base_image_path is not None:
        with open(base_image_path, "rb") as fh:
            base_sha = hashlib.sha256(fh.read()).hexdigest()
    report = validate_render_input(scene, canonical, base_meta, base_sha, attempt_meta)
    report.setdefault("floor_plan_id", file_id)
    return report
